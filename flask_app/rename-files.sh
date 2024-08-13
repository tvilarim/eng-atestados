#!/bin/bash

# Loop over all files in the current directory
for file in *; do
    # Only process files (ignore directories)
    if [[ -f "$file" ]]; then
        # Use parameter expansion to create the new filename
        new_name=$(echo "$file" | tr -c '[:alnum:]' '_' | tr -s '_')

        # Rename the file if the name changes
        if [[ "$file" != "$new_name" ]]; then
            mv "$file" "$new_name"
            echo "Renamed '$file' to '$new_name'"
        else
            echo "No change for '$file'"
        fi
    fi
done
