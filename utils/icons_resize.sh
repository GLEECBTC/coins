#!/bin/bash

set -euo pipefail

scriptpath="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
TARGET_SIZE="128x128"
ICON_DIR="./icons"
ORIGINAL_ICON_DIR="./icons_original"
HASH_FILE="./utils/icon_checksums.json"

cd $scriptpath
cd ..

# Function to calculate file checksum
calculate_checksum() {
    local file="$1"
    if [[ -f "$file" ]]; then
        sha256sum "$file" | cut -d' ' -f1
    else
        echo ""
    fi
}

# Function to read existing checksums
read_checksums() {
    if [[ -f "$HASH_FILE" ]]; then
        cat "$HASH_FILE"
    else
        echo "{}"
    fi
}

# Function to write checksums
write_checksums() {
    local checksums="$1"
    echo "$checksums" > "$HASH_FILE"
}

# Function to get checksum from JSON
get_checksum_from_json() {
    local json="$1"
    local key="$2"
    echo "$json" | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    print(data.get('$key', {}).get('original', ''))
    print(data.get('$key', {}).get('processed', ''))
except:
    print('')
    print('')
"
}

# Function to update checksum in JSON
update_checksum_in_json() {
    local json="$1"
    local key="$2"
    local original_checksum="$3"
    local processed_checksum="$4"
    echo "$json" | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
except:
    data = {}
data['$key'] = {'original': '$original_checksum', 'processed': '$processed_checksum'}
print(json.dumps(data, indent=2))
"
}

# Function to remove checksum entry from JSON
remove_checksum_from_json() {
    local json="$1"
    local key="$2"
    echo "$json" | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    if '$key' in data:
        del data['$key']
    print(json.dumps(data, indent=2))
except:
    print('{}')
"
}

# Function to get all keys from JSON
get_all_keys_from_json() {
    local json="$1"
    echo "$json" | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    for key in data.keys():
        print(key)
except:
    pass
"
}

echo "🔍 Analyzing icon files and checksums..."

# Read existing checksums
CHECKSUMS=$(read_checksums)

# Check for orphaned entries (icons that exist in checksums but not in icons_original)
echo "🧹 Checking for orphaned entries in checksums database..."
ORPHANED_ENTRIES=()
while IFS= read -r key; do
    if [[ -n "$key" && ! -f "$ORIGINAL_ICON_DIR/$key" ]]; then
        ORPHANED_ENTRIES+=("$key")
    fi
done <<< "$(get_all_keys_from_json "$CHECKSUMS")"

# Remove orphaned entries and corresponding processed files
if [ ${#ORPHANED_ENTRIES[@]} -gt 0 ]; then
    echo "🗑️  Found ${#ORPHANED_ENTRIES[@]} orphaned entries to clean up:"
    for entry in "${ORPHANED_ENTRIES[@]}"; do
        echo "  - $entry"
        
        # Remove from checksums
        CHECKSUMS=$(remove_checksum_from_json "$CHECKSUMS" "$entry")
        
        # Remove processed file if it exists
        processed_file="$ICON_DIR/$entry"
        if [[ -f "$processed_file" ]]; then
            rm "$processed_file"
            echo "    ➤ removed processed file: $processed_file"
        fi
    done
else
    echo "✅ No orphaned entries found in checksums database."
fi

# Find files that need processing
FILES_TO_PROCESS=()
PROCESS_REASONS=()

while IFS= read -r -d '' file; do
    relative_path="${file#$ORIGINAL_ICON_DIR/}"
    processed_file="$ICON_DIR/$relative_path"
    
    # Calculate current checksums
    original_checksum=$(calculate_checksum "$file")
    processed_checksum=$(calculate_checksum "$processed_file")
    
    # Get stored checksums
    checksums_info=$(get_checksum_from_json "$CHECKSUMS" "$relative_path")
    stored_original=$(echo "$checksums_info" | sed -n '1p')
    stored_processed=$(echo "$checksums_info" | sed -n '2p')
    
    # Determine if processing is needed
    needs_processing=false
    reason=""
    
    if [[ ! -f "$processed_file" ]]; then
        needs_processing=true
        reason="missing processed file"
    elif [[ "$original_checksum" != "$stored_original" ]]; then
        needs_processing=true
        reason="original file changed"
    elif [[ "$processed_checksum" != "$stored_processed" ]]; then
        needs_processing=true
        reason="processed file changed/corrupted"
    fi
    
    if $needs_processing; then
        FILES_TO_PROCESS+=("$relative_path")
        PROCESS_REASONS+=("$reason")
    fi
done < <(find "$ORIGINAL_ICON_DIR" -name "*.png" -type f -print0)

if [ ${#FILES_TO_PROCESS[@]} -eq 0 ]; then
    echo "✅ No files need processing. All icons are up to date."
    exit 0
fi

echo "📋 Found ${#FILES_TO_PROCESS[@]} files to process:"
for i in "${!FILES_TO_PROCESS[@]}"; do
    echo "  - ${FILES_TO_PROCESS[$i]} (${PROCESS_REASONS[$i]})"
done

echo "📁 Processing files from icons_original to icons..."
for file in "${FILES_TO_PROCESS[@]}"; do
    target_dir="$ICON_DIR/$(dirname "$file")"
    mkdir -p "$target_dir"
    cp "$ORIGINAL_ICON_DIR/$file" "$ICON_DIR/$file"
    echo "  ➤ copied: $file"
done

echo "🧹 Processing images in icons directory..."
cd $ICON_DIR
for file in "${FILES_TO_PROCESS[@]}"; do
    echo "  ➤ mogrify: $file"
    # Needs imagemagick installed: sudo apt install imagemagick
    # Resize proportionally to fit within 128x128 (only shrink, never upscale), then pad with transparent background
    filename="$(basename "$file")"
    if [[ "$filename" == "base.png" ]]; then
        # Preserve the white border on base.png by skipping -trim
        mogrify -background transparent -strip +repage -fuzz 0% -resize ${TARGET_SIZE}\> -gravity center -extent $TARGET_SIZE "$file"
    else
        mogrify -background transparent -strip -trim +repage -fuzz 20% -resize ${TARGET_SIZE}\> -gravity center -extent $TARGET_SIZE "$file"
    fi
done

echo "📦 Optimizing processed images with oxipng..."
for file in "${FILES_TO_PROCESS[@]}"; do
    echo "  ➤ oxipng: $file"
    # https://github.com/oxipng/oxipng/releases install from here
    oxipng -o 6 --zopfli --strip all "$file"
done

cd ..

echo "💾 Updating checksums database..."
for file in "${FILES_TO_PROCESS[@]}"; do
    original_file="$ORIGINAL_ICON_DIR/$file"
    processed_file="$ICON_DIR/$file"
    
    original_checksum=$(calculate_checksum "$original_file")
    processed_checksum=$(calculate_checksum "$processed_file")
    
    CHECKSUMS=$(update_checksum_in_json "$CHECKSUMS" "$file" "$original_checksum" "$processed_checksum")
done

# Write updated checksums to file
write_checksums "$CHECKSUMS"

echo "✅ Successfully processed ${#FILES_TO_PROCESS[@]} files and updated checksums database."
