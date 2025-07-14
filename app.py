import streamlit as st
import openstudio
import pandas as pd
import os
import tempfile
from typing import Optional

# --- Function to load OSM model (WITH CACHING using st.cache_resource) ---


@st.cache_resource
def load_osm_file_as_model(osm_file_path: str, version_translator: Optional[bool] = True) -> openstudio.model.Model:
    """Loads an OSM file into an OpenStudio model.

    Args:
        osm_file_path: The path to the OSM file. This can be a relative path
            or an absolute path.
        version_translator: Whether to use the OpenStudio version translator.
            This is necessary if the OSM file is in a version of OpenStudio
            that is different from the version of OpenStudio that is being used
            to load the file. Defaults to True.

    Returns:
        An OpenStudio model containing the data from the OSM file.
    """
    # Get the absolute path to the OSM file.
    osm_file_path = os.path.abspath(osm_file_path)

    if version_translator:
        translator = openstudio.osversion.VersionTranslator()
        osm_model = translator.loadModel(osm_file_path).get()
    else:
        # Note: The original code had a duplicate call here.
        # It's kept as per your instruction to not change logic unless necessary,
        # but typically you'd only have one of these lines if 'openstudio.path.to' works.
        osm_model = openstudio.model.Model.load(osm_file_path).get()
        # This line was problematic and is commented out based on prior discussions.
        # osm_model = openstudio.model.Model.load(openstudio.path.to(osm_file_path)).get()

    print(
        f"The OSM read file contains data for the {osm_model.building().get().name()}")
    # Return the OpenStudio model.
    return osm_model

# --- Function to process model objects and extract methods/data (WITH CACHING using st.cache_resource) ---


@st.cache_resource
# Changed 'model' to '_model'
def process_model_objects(_model: openstudio.model.Model):
    """Processes the OpenStudio model to extract unique object types,
    their methods, and sample object handles.

    Args:
        _model: The loaded OpenStudio model. (Argument prefixed with underscore for caching)

    Returns:
        A tuple containing:
        - df_sorted (pd.DataFrame): Sorted DataFrame of object types and methods.
        - sample_object_handles (dict): Dictionary of sample handles for each object class.
    """
    all_model_objects = _model.getModelObjects()  # Use _model here
    unique_object_types = {}
    sample_object_handles = {}

    progress_text = "Analyzing objects and collecting methods..."
    my_bar = st.progress(0, text=progress_text)

    total_objects = len(all_model_objects)
    processed_count = 0

    for obj in all_model_objects:
        obj_class = obj.iddObjectType().valueDescription()
        obj_handle = obj.handle()
        dynamic_method_name = obj_class.replace(
            "OS:", "to_").replace(":", "").strip()

        if obj_class not in unique_object_types and obj_class.startswith("OS:"):
            if obj_class not in sample_object_handles:
                sample_object_handles[obj_class] = obj_handle

            unique_object_types[obj_class] = []
            obj_ = _model.getModelObject(obj_handle).get()  # Use _model here

            try:
                specific_obj_optional = getattr(obj_, dynamic_method_name)()
                try:
                    if specific_obj_optional.is_initialized():
                        specific_obj = specific_obj_optional.get()
                except:
                    specific_obj = obj_

                all_members = dir(specific_obj)
                methods = [
                    m for m in all_members
                    if not (m.startswith('_') or m.startswith('to_')) and
                    callable(getattr(specific_obj, m, None))
                ]
                unique_object_types[obj_class] = sorted(methods)
            except Exception as e:
                unique_object_types[obj_class] = [
                    f"Error getting methods: {e}"]

        processed_count += 1
        my_bar.progress(processed_count / total_objects, text=progress_text)

    my_bar.empty()

    # Prepare data for the table
    data = []
    for obj_class, methods in unique_object_types.items():
        class_name = obj_class
        data.append({
            "Object Type (Class)": class_name,
            "Available Methods": ", ".join(methods) if methods else "No public methods"
        })

    processed_data = []
    for entry in data:
        string_value = list(entry.values())[0]
        comma_separated_string = list(entry.values())[1]
        list_of_strings = [item.strip()
                           for item in comma_separated_string.split(',')]

        for item in list_of_strings:
            row_data = {}
            keys = list(entry.keys())
            row_data[keys[0]] = string_value
            row_data[keys[1]] = item
            processed_data.append(row_data)

    df = pd.DataFrame(processed_data)
    df_sorted = df.sort_values(by="Object Type (Class)").reset_index(drop=True)

    return df_sorted, sample_object_handles


# --- Streamlit Page Configuration ---
st.set_page_config(layout="wide", page_title="OpenStudio Methods Explorer")

st.title("🔎 OpenStudio Object Methods Explorer")

# --- Sidebar for OSM File Upload ---
with st.sidebar:
    st.header("Upload Model")
    st.write("Upload an `.osm` model to view available methods for each object type.")
    uploaded_file = st.file_uploader("Upload your .osm file", type="osm")
    st.markdown("---")

    # --- Moved loading messages to sidebar ---
    if uploaded_file is not None:
        # Use tempfile to create a temporary file securely
        with tempfile.NamedTemporaryFile(delete=False, suffix=".osm") as tmp_file:
            tmp_file.write(uploaded_file.getbuffer())
            file_path = tmp_file.name

        try:
            st.write(f"Loading model: `{uploaded_file.name}`...")

            # Load the model (now cached with st.cache_resource)
            model = load_osm_file_as_model(file_path)

            st.success("Model loaded successfully. ✔️")

            # Process model objects (now cached with st.cache_resource, and model argument is ignored for hashing)
            df_sorted, sample_object_handles = process_model_objects(model)

            # Store processed data in session state to make it available outside the sidebar context
            st.session_state['df_sorted'] = df_sorted
            st.session_state['sample_object_handles'] = sample_object_handles
            st.session_state['model'] = model  # Store model for later use

        except Exception as e:
            st.error(f"❌ An error occurred while processing the model: {e}")
            st.info(
                "Ensure that the `.osm` file is valid and that your OpenStudio SDK installation is correct.")
            # Clear session state if an error occurs to prevent partial data issues
            if 'df_sorted' in st.session_state:
                del st.session_state['df_sorted']
            if 'sample_object_handles' in st.session_state:
                del st.session_state['sample_object_handles']
            if 'model' in st.session_state:
                del st.session_state['model']
        finally:
            # Clean up the temporary file
            if os.path.exists(file_path):
                os.remove(file_path)

# --- Main Content Area ---
# Check if data is available in session state before rendering main content
if 'df_sorted' in st.session_state and 'sample_object_handles' in st.session_state and 'model' in st.session_state:
    df_sorted = st.session_state['df_sorted']
    sample_object_handles = st.session_state['sample_object_handles']
    model = st.session_state['model']  # Retrieve model from session state

    # --- Header and Filters span full width ---
    st.info("💡 **Tip:** This tool provides a quick overview of the OpenStudio API for classes present in your model, ideal for automation script development! ✨")
    st.markdown("---")

    if not df_sorted.empty:
        st.markdown("##### 🎯 Filters")

        # Create columns for the filters to put them on the same line
        filter_col1, filter_col2 = st.columns(
            [0.4, 0.6])  # Two columns of equal width

        with filter_col1:
            class_options = ["All"] + \
                list(df_sorted["Object Type (Class)"].unique())
            selected_class = st.selectbox(
                "Filter by Object Type (Class)", class_options)

        with filter_col2:
            method_keyword = st.text_input(
                "Search methods by keyword (e.g., 'set', 'get')", "")

        df_filtered = df_sorted.copy()

        if selected_class != "All":
            df_filtered = df_filtered[df_filtered["Object Type (Class)"]
                                      == selected_class]

        if method_keyword:
            df_filtered = df_filtered[df_filtered["Available Methods"].str.contains(
                method_keyword, case=False, na=False)]

        st.write(f"Showing {len(df_filtered)} of {len(df_sorted)} rows.")
    else:
        st.info("No objects found in the model. 🤷‍♂️")
        # Ensure selected_class is defined even if df_sorted is empty, for the expander logic
        selected_class = "All"  # Default to "All" if no data

    # --- Two columns below filters ---
    # col1 for table (40%), col2 for example (60%) as requested
    col1, col2 = st.columns([0.4, 0.6])

    with col1:
        if not df_sorted.empty:  # Only show table if data exists
            st.dataframe(df_filtered, height=500, use_container_width=True)
        else:
            pass  # Message already handled above, no need for redundant info here

    with col2:
        # --- Display Sample Object (Conditional/Expandable) ---
        expander_title = f"Selected Object Type: `{selected_class}`" if selected_class != "All" else "Select an Object Type to see an example"

        # The expander is initially open if a specific class is selected, closed if "All"
        with st.expander(expander_title, expanded=(selected_class != "All")):
            if selected_class == "All":
                st.info(
                    "Select an 'Object Type (Class)' from the filter to see an example object here. 👈")
            elif selected_class in sample_object_handles:
                try:
                    sample_handle = sample_object_handles[selected_class]
                    example_object = model.getModelObject(sample_handle).get()

                    st.write(
                        f"**Name:** `{example_object.nameString() if example_object.nameString() else 'N/A (no name)'}`")
                    # st.write(f"**Handle (UUID):** `{example_object.handle().__str__()}`")
                    # st.write(f"**Type (IDD):** `{example_object.iddObjectType().valueDescription()}`")

                    st.write(f"**Object Text (IDF Format):**")
                    # User's preferred method for displaying object text (as confirmed works for them)
                    st.code(f"{example_object}")

                except Exception as e:
                    st.error(
                        f"Failed to retrieve or display example object for `{selected_class}`: {e}")
            # Fallback for edge cases where class might be selected but no handle found (shouldn't happen with current logic)
            else:
                st.info(
                    f"No example object found for type: `{selected_class}`.")
else:
    st.info("Please upload an OpenStudio model (.osm) in the sidebar to begin. ⬆️")
