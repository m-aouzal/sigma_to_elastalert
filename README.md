
This folder contains a pipeline that:

1. **Converts Sigma rules** from the `sigma/rules/windows` folder into Elastalert-compatible YAML files.
2. **Performs partial transformations** on those converted files (e.g. lowercasing certain values, converting `description:` lines to block scalars, replacing `index: "*"` with `index: "winlogbeat-*"`, and appending `.keyword` to ECS fields in the query strings).
3. **Prepares** final Elastalert rules that can be used in an Elasticsearch + Kibana environment.

Below is an overview of the important files/folders and how they all fit together:

---

## Folder & File Overview

- **`check_keywords.py`**  
  This script (if present) may have once been used to verify or debug `.keyword` usage. It's not directly invoked by `convert.sh` now, but can be repurposed for checking fields.

- **`pySigma-backend-elasticsearch/`**  
  A custom or experimental Sigma backend for Elasticsearch. Typically, this is used in tandem with `sigma convert -t elastalert ...`. However, note that advanced features or new ES versions (like Elasticsearch 8+) may cause issues in older PySigma code. This is partly why the `.keyword` transformations were introduced – so that older Sigma backends can still produce functional queries on new indexes.

- **`converted_sigma_rules_to_elastalert/`**  
  This is the output folder where `convert.sh` places the final Elastalert rules after transformation. The subfolders mirror the structure from `sigma/rules/windows`. If everything succeeds, you’ll find .yml files in here containing the final rules.

- **`convert.sh`**  
  The main script that orchestrates the entire pipeline. It:
  1. Loads each `.yml` Sigma rule from `RULE_DIR` (by default `./sigma/rules/windows/`).
  2. Runs `sigma convert` on them, partially lowercasing the detection block values.
  3. Fixes the `description:` lines by turning them into a YAML block scalar.
  4. Replaces `index: "*"` with `index: "winlogbeat-*"`.
  5. Uses AWK to scan lines that start with `query:` or `query_string:` and appends `.keyword` to ECS fields in that line – only if they match a certain pattern (e.g. `winlog.channel`) and are not exempt.

- **`non_keyword_fields`**  
  This file contains a list of fields **not** to be appended with `.keyword`. If a field is in here, `convert.sh`’s final AWK transformation will skip adding `.keyword` to it.

gma.


---

## What `convert.sh` Does

### 1. **Partial Lowercasing for Case-Insensitive Matching**

In older or simpler Sigma backends, you might want a case-insensitive search. However, because these fields become keywords in Elasticsearch, you want them stored in a consistent lowercased format. Specifically:

- The script uses sed to:
  - Enter the detection block: from `detection:` until the next top-level key.
  - Skip lines starting with `condition:` (so the condition is not lowercased).
  - Lowercase everything else in that block.

Why lowercasing?  
- Keywords in Elasticsearch are exact-match. If you want consistent, case-insensitive searching, it’s easiest to store them in lowercased form. Or, if a normalizer is used, it can also forcibly lowercase at index time.

### 2. **Converting `description:` Lines to a Block Scalar**

YAML’s plain scalar lines can break if they contain certain punctuation or colons. The script uses AWK to:

- Detect lines starting with `description:`
- Output `description: |` 
- Indent subsequent lines of the description so it’s recognized as a multi-line block scalar.

### 3. **Replacing `index: "*"` with `index: "winlogbeat-*"`**

Originally, Sigma rules might have `index: "*"`. But many users store logs in a named pattern like `winlogbeat-*`. The script finds lines that begin with `index:` and replaces `'*'` with `"winlogbeat-*"`. This helps ensure the generated Elastalert rules only target the correct indices.

### 4. **Appending `.keyword` to ECS Fields in the Query**

Because new versions of Elasticsearch do not accept partial text searching on keyword fields (or older PySigma backends might rely on `field:value` logic that doesn’t map well to new text fields), we do:

- AWK scans lines starting with `query:` or `query_string:`.
- We find tokens that look like `field:` or `field.xyz:`.
- If the field matches the ECS-like pattern (`^[a-zA-Z_]+(\.[a-zA-Z0-9_]+)+$`) and is **not** in an exemption list, we append `.keyword`. For example, `winlog.channel` becomes `winlog.channel.keyword`.
- This ensures that searching on certain fields is done as a keyword, not as a text field. The script helps older rules remain functional in new ES setups.

### 5. **Parallel Execution**

The script uses `GNU Parallel` to process multiple rules concurrently (`-j 10` by default). If any file fails, it logs that in `./failed_conversion`. At the end, it prints a summary of failed or invalid ones.

---

## Why `.keyword` and Lowercasing?

1. **`.keyword`**  
   In modern Elasticsearch, fields stored as `text` are analyzed and used for full-text search. If you want an exact-match filter (like `field:"someValue"`), it’s more stable to store them as a **keyword** field. That’s why we do `field.keyword`. This is standard in the ECS (Elastic Common Schema) world, especially if you want to do exact matching or aggregations.

2. **Lowercasing**  
   If you want case-insensitive searches (like matching `PROCESS.EXECUTABLE` or `Process.Executable` or `process.executable` equally), the simplest approach is to store them all as lowercased keywords. Then you only have to search in lowercase. Alternatively, you can use a normalizer on the field to make everything lowercase at index time.

Below is an example snippet you can place in your index template or dev console to define a **normalizer** that lowercases all keyword fields:

```json
PUT winlogbeat-*
{
  "settings": {
    "analysis": {
      "normalizer": {
        "lowercase_normalizer": {
          "type": "custom",
          "filter": ["lowercase"]
        }
      }
    }
  },
  "mappings": {
    "dynamic_templates": [
      {
        "strings_as_text_with_keyword": {
          "match_mapping_type": "string",
          "mapping": {
            "type": "text",
            "fields": {
              "keyword": {
                "type": "keyword",
                "normalizer": "lowercase_normalizer"
              }
            }
          }
        }
      }
    ]
  }
}
```

With this approach, the **`.keyword`** subfield is always stored in lowercase. That means searching for `FIELD.KEYWORD:"SomeValue"` is effectively searching for `somevalue`, making it case-insensitive.

---

## Reindexing Older Data

If you have older indices (e.g. `winlogbeat-8.17.4`) that don’t have the normalizer or the new field mappings, you can use:

```json
POST _reindex
{
  "source": {
    "index": "winlogbeat-8.17.4"
  },
  "dest": {
    "index": "winlogbeat-8.17.4-2025.03.29"
  }
}
```

This copies data from `winlogbeat-8.17.4` to a new index `winlogbeat-8.17.4-2025.03.29` which presumably has the new mapping (with the normalizer). Then you can point your queries or Kibana index patterns at that new index. 

**Hint**: If you paste large JSON in Kibana Dev Tools, ensure it’s in pure JSON format, not YAML.  

---

## Summary

- **`convert.sh`** automates the process of converting and massaging Sigma rules into functional Elastalert rules for an ECS + Elasticsearch environment.  
- We do partial lowercasing, block-scalar descriptions, index rewriting, and `.keyword` appending.  
- The approach helps older or simpler Sigma backends remain useful with new ES 8 versions.  
- For actual data, you might need to define a normalizer or do reindexing to ensure your fields exist as lowercased keywords. Otherwise, your queries might not match.  

We hope this clarifies how to use the scripts and why `.keyword` plus lowercasing is important for stable, case-insensitive searching in modern Elasticsearch.
if you have any question reach me out here : aouzal.mohamed@outlook.com
