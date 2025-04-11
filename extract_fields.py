#!/usr/bin/env python3
"""
extract_rule_fields.py

This script recursively searches a directory for occurrences of self.rule.get('...')
and collects the field names from the ElastAlert code. It then prints a sorted list
and (optionally) outputs a YAML dictionary mapping each field to a null value (so that
the output appears as “key:” without a value).
  
Usage:
    python extract_rule_fields.py --dir /path/to/elastalert_modules --output fields.yml

If --output is not provided, the fields are printed to STDOUT.
"""

import argparse
import os
import re
from ruamel.yaml import YAML

# Regular expression pattern to capture keys used in self.rule.get('KEY', ...)
PATTERN = re.compile(r"self\.rule\.get\(\s*['\"]([^'\"]+)['\"]")

def extract_fields_from_file(filepath):
    """
    Opens the file and uses a regex to extract all field names from self.rule.get('field', ...).
    Returns a set of fields found.
    """
    fields = set()
    try:
        with open(filepath, 'r') as f:
            contents = f.read()
    except Exception as e:
        print(f"Error reading file {filepath}: {e}")
        return fields

    found = PATTERN.findall(contents)
    for field in found:
        fields.add(field.strip())
    return fields

def extract_fields_from_dir(directory):
    """
    Walks the given directory and extracts all unique field names from Python files.
    """
    all_fields = set()
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith(".py"):
                filepath = os.path.join(root, file)
                file_fields = extract_fields_from_file(filepath)
                all_fields.update(file_fields)
    return all_fields

def main():
    parser = argparse.ArgumentParser(
        description="Extract rule field keys from ElastAlert source using 'self.rule.get' patterns."
    )
    parser.add_argument("--dir", required=True, help="Directory to search (recursively) for .py files")
    parser.add_argument("--output", help="If provided, output the field dictionary to a YAML file")
    args = parser.parse_args()

    fields = extract_fields_from_dir(args.dir)
    fields = sorted(fields)

    # Create a dictionary mapping each field to None so that when dumped,
    # it appears as key:  (with nothing after the colon)
    field_dict = {field: None for field in fields}

   
    
    

    # Configure ruamel.yaml to dump in block style.
    yaml_parser = YAML(typ='rt')
    yaml_parser.default_flow_style = False

    # Custom representer for None: output as an empty scalar (nothing after the colon)
    def represent_none(dumper, data):
        return dumper.represent_scalar('tag:yaml.org,2002:null', '')
    yaml_parser.representer.add_representer(type(None), represent_none)

    if args.output:
        try:
            with open(args.output, 'w') as f_out:
                yaml_parser.dump(field_dict, f_out)
            print(f"Extracted fields dictionary written to {args.output}")
        except Exception as e:
            print(f"Error writing output file: {e}")
    else:
        yaml_parser.dump(field_dict, sys.stdout)

if __name__ == "__main__":
    main()

