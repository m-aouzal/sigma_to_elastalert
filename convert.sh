#!/bin/bash

# ========== CONFIG ==========
RULE_DIR="./sigma/rules/windows/"
OUTPUT_DIR="./converted_sigma_rules_to_elastalert"
EXEMPTION_FILE="./non_keyword_fields"
FAIL_LIST="./failed_conversion"
JOBS=10  # Number of parallel jobs

mkdir -p "$OUTPUT_DIR"
> "$FAIL_LIST"  # Empty the fail list file at start

# ========== FUNCTION: process_rule ==========
process_rule() {
    rule="$1"
    echo "Processing rule: $rule"

    relative_path=$(realpath --relative-to="$RULE_DIR" "$rule")
    output_file="$OUTPUT_DIR/$relative_path"
    mkdir -p "$(dirname "$output_file")"

    temp_output=$(mktemp)
    temp_err=$(mktemp)

    # STEP 1: Sigma conversion with partial lowercasing (skips condition:)
    sigma convert \
        -t elastalert \
        -p ecs_windows \
        --disable-pipeline-check \
        <(
          sed -E '
            /^[[:space:]]*detection:/,/^[^[:space:]]/ {
                /^[[:space:]]*condition:/ b keep
                s/^([[:space:]]*[^:]+:[[:space:]]*)(.*)$/\1\L\2\E/g;
                s/^([[:space:]]*-[[:space:]]*)(.*)$/\1\L\2\E/g;
                :keep
            }
          ' "$rule"
        ) 2> "$temp_err" \
    > "$temp_output"

    if [ $? -ne 0 ]; then
        echo "Error converting $rule"
        echo "$rule: Error converting sigma rule: $(cat "$temp_err")" >> "$FAIL_LIST"
        rm -f "$temp_output" "$temp_err"
        return
    fi
    echo "Successfully converted $rule -> $temp_output"
    rm -f "$temp_err"

    # STEP 2: Turn description lines into a block scalar
    temp_fixed_description=$(mktemp)
    awk '
    BEGIN { in_desc=0 }
    /^[[:space:]]*description:/ {
        print "description: |"
        sub(/^[[:space:]]*description:[[:space:]]*/, "")
        if(length($0) > 0) {
            print "  " $0
        }
        in_desc=1
        next
    }
    in_desc {
        if($0 ~ /^[a-zA-Z]+:/) { in_desc=0; print $0; next }
        else { print "  " $0; next }
    }
    { print }
    ' "$temp_output" > "$temp_fixed_description"

    if [ $? -ne 0 ]; then
        echo "Error fixing description in $rule"
        echo "$rule: Error fixing description" >> "$FAIL_LIST"
        rm -f "$temp_output" "$temp_fixed_description"
        return
    fi
    echo "Successfully fixed description for $rule"
    rm -f "$temp_output"

    # STEP 2.5: Replace index "*" with "winlogbeat-*"
    sed -i -E "s/(index:[[:space:]]*)['\"]?[*]['\"]?/\1\"winlogbeat-*\"/" "$temp_fixed_description"

    # STEP 3: Awk pass to append .keyword and lowercase winlog.channel.keyword value
    temp_final=$(mktemp)
    awk -v exFile="$EXEMPTION_FILE" '
    ###############################################################################
    # Read the exemption list from exFile into an array "exempt".
    ###############################################################################
    BEGIN {
        while ((getline line < exFile) > 0) {
            gsub(/^[[:space:]]+|[[:space:]]+$/, "", line)
            if (length(line) > 0) {
                exempt[line] = 1
            }
        }
    }

    ###############################################################################
    # Helper: ends_with_keyword(f)
    # Returns true if the field f ends with ".keyword".
    ###############################################################################
    function ends_with_keyword(f) {
        n = length(f)
        return (n >= 8 && substr(f, n-7) == ".keyword")
    }

    ###############################################################################
    # Helper: valid_ecs_field(f)
    # Returns true if the field matches the requested ECS pattern
    ###############################################################################
    function valid_ecs_field(f) {
        return (f ~ /^[a-zA-Z_]+(\.[a-zA-Z0-9_]+)+$/)
    }

    ###############################################################################
    # Process the query string: append .keyword and lowercase winlog.channel.keyword value
    ###############################################################################
    function process_query(q) {
        result = ""
        while (length(q) > 0) {
            # Match an ECS field followed by a colon (e.g., winlog.channel:)
            if (match(q, /([a-zA-Z_]+\.[a-zA-Z_]+(\.[a-zA-Z0-9_]+)*):/)) {
                field = substr(q, RSTART, RLENGTH - 1)  # Exclude the colon
                rest = substr(q, RSTART + RLENGTH)
                before = substr(q, 1, RSTART - 1)

                # Append .keyword if conditions are met
                if (!(field in exempt) && !ends_with_keyword(field) && valid_ecs_field(field)) {
                    field = field ".keyword"
                }

                # Extract the value up to an unescaped space or end
                value = ""
                i = 1
                while (i <= length(rest)) {
                    char = substr(rest, i, 1)
                    if (char == "\\" && i < length(rest) && substr(rest, i+1, 1) == " ") {
                        value = value "\\ "
                        i += 2
                    } else if (char == " " || char == "\t") {
                        break
                    } else {
                        value = value char
                        i++
                    }
                }
                after = substr(rest, i)

                # Lowercase the value if the field is winlog.channel.keyword
                if (field == "winlog.channel.keyword") {
                    value = tolower(value)
                }

                result = result before field ":" value
                q = after
            } else {
                # No more fields, append the rest
                result = result q
                break
            }
        }
        return result
    }

    ###############################################################################
    # Main logic: Process lines starting with query: or query_string:
    ###############################################################################
    {
        match($0, /^[[:space:]]*(query|query_string):[[:space:]]*/)
        if (RSTART == 1) {
            prefix = substr($0, RSTART, RLENGTH)
            query = substr($0, RSTART + RLENGTH)

            # Remove leading/trailing quotes if present
            if (query ~ /^".*"$/) {
                quoted = 1
                query = substr(query, 2, length(query) - 2)
            } else {
                quoted = 0
            }

            # Process the query
            processed_query = process_query(query)

            # Reconstruct the line
            if (quoted) {
                print prefix "\"" processed_query "\""
            } else {
                print prefix processed_query
            }
        } else {
            print $0
        }
    }
    ' "$temp_fixed_description" > "$temp_final"

    if [ $? -ne 0 ]; then
        echo "Error in AWK post-processing for $rule"
        echo "$rule: AWK post-processing failed" >> "$FAIL_LIST"
        rm -f "$temp_fixed_description" "$temp_final"
        return
    fi

    mv "$temp_final" "$output_file"
    rm -f "$temp_fixed_description"
}

# ========== Export and Parallel ==========
export -f process_rule
export RULE_DIR
export OUTPUT_DIR
export EXEMPTION_FILE
export FAIL_LIST
export JOBS

# Run the processing function in parallel
find "$RULE_DIR" -type f -name "*.yml" | parallel -j "$JOBS" process_rule {}

# Summarize failures
if [ -s "$FAIL_LIST" ]; then
    echo ""
    echo "=== The following rules failed conversion or post-processing: ==="
    sort -u "$FAIL_LIST"
else
    echo ""
    echo "All rules processed successfully!"
fi

rm -f "$FAIL_LIST"
