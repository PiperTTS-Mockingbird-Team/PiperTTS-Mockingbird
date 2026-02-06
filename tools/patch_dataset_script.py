
import os

path = r'make piper voice models/tts_dojo/girlll_dojo/scripts/link_dataset.sh'

with open(path, 'rb') as f:
    content = f.read().replace(b'\r\n', b'\n')

content_str = content.decode('utf-8')

new_logic = """
# MAIN PROGRAM

# --- MODIFIED: Check for local dataset first ---
LOCAL_DATASET_DIR="../dataset"
# We count wavs to see if it is populated
count=$(find -L "$LOCAL_DATASET_DIR" -maxdepth 1 -type f \( -iname "*.wav" \) | wc -l)

if [ -d "$LOCAL_DATASET_DIR" ] && [ "$count" -gt 0 ]; then
    echo "Found local dataset in $LOCAL_DATASET_DIR with $count files. Using it."
    selected_dataset_dir="$LOCAL_DATASET_DIR"
    NAME="local_dataset"
    DESCRIPTION="Local dataset for this dojo"
    
    # We skip menu and configuration file loading
    dataset_path_relative="../dataset"
    
    # Defaults for "Easy Mode"
    quality="M"
    scratch="false"
    
    # We skip getting quality/scratch choice to make it fully automatic if desired, 
    # OR we can keep them if we want the user to choose.
    # For now, let's keep them so the user knows what's happening, 
    # but the previous error happened before this point.
    
    get_quality_choice
    get_scratch_choice
    
    # skip finding default checkpoint if training from scratch.
    if [ $scratch == "false" ]; then 
        find_default_checkpoint_dir
        relative_find_default_checkpoint_file
    else
        default_checkpoint_path=""
    fi
     
    # Manually perform what relative_link_files does, but simpler for local
    if [ "$quality" = "L" ]; then
        sampling_rate=16000
    else
        sampling_rate=22050
    fi
    
    # Default to assuming folder has wavs directly
    audio_dir="$dataset_path_relative"
    metadata_path="$dataset_path_relative/metadata.csv"

    echo
    echo "Source audio directory         : $audio_dir"
    echo "metadata.csv location          : $metadata_path"
    echo
    
    # Create symlinks
    if [ -d "$audio_dir" ]; then
        $(remove_existing_symlink "$AUDIO_DIR_SYMLINK")
        ln -s "$audio_dir" "$AUDIO_DIR_SYMLINK"
    fi
    if [ -f "$metadata_path" ]; then
        $(remove_existing_symlink "$METADATA_PATH_SYMLINK")
        ln -s "$metadata_path" "$METADATA_PATH_SYMLINK" 
    fi
    
    # Handle checkpoint linking
    if [ $scratch == "false" ]; then
        checkpoint_filename=$(basename $default_checkpoint_path)
        checkpoint_symlink="${DEFAULT_CHECKPOINT_DIR_SYMLINK}${checkpoint_filename}"
        remove_previous_checkpoint $DEFAULT_CHECKPOINT_DIR_SYMLINK
        $(remove_existing_symlink "$checkpoint_symlink")
        if [ -f "$default_checkpoint_path" ]; then
            ln -s "$default_checkpoint_path" "$checkpoint_symlink"
        fi
    fi
    
    write_varfiles
    exit 0
fi
# --- END MODIFIED ---

populate_menu
"""

# Only patch if not already patched
if '# --- MODIFIED: Check for local dataset first ---' not in content_str:
    if '# MAIN PROGRAM' in content_str:
        parts = content_str.split('# MAIN PROGRAM')
        # We replace the marker with marker + new logic
        new_content = parts[0] + new_logic + parts[1]
        
        # Ensure line endings are LF
        final_content = new_content.replace('\r\n', '\n').encode('utf-8')
        
        with open(path, 'wb') as f:
            f.write(final_content)
        print('Patched link_dataset.sh for local dataset support')
    else:
        print('Could not find MAIN PROGRAM marker')
else:
    print('Already patched.')
