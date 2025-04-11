#!/usr/bin/env python3
"""
modify_alert_section.py

This script modifies the alert section of ElastAlert rule YAML file(s) based on a provided new alert configuration
and a "valid alert fields" dictionary.

There are two modes:

1. Append Mode (--mode append): For every key in the new alert section that is present in the rule and is a valid alert key,
   update its value.
2. Override Mode (--mode override): Remove any alert-related keys (as determined by the valid alert fields dictionary)
   from the rule, then insert all keys from the new alert section.

Before any changes, the script validates the new alert configuration: every key in the new alert configuration must
be present in the valid alert fields dictionary—otherwise, an error is returned, unless the --force flag is provided.

Usage examples:
  # Append mode (only update matching alert keys) on a single file:
  python modify_alert_section.py --input rule.yml --alertfile new_alert.yml --validfile alerts_fields.yml --mode append --output updated_rule.yml

  # Override mode (replace entire alert section) on a directory of rules:
  python modify_alert_section.py --input /path/to/rules --alertfile new_alert.yml --validfile alerts_fields.yml --mode override --output /path/to/updated_rules

The script uses ruamel.yaml in round-trip mode to preserve formatting.
"""

import argparse
import os
import sys
from ruamel.yaml import YAML

def load_yaml(filepath, yaml_instance):
    try:
        with open(filepath, "r") as f:
            return yaml_instance.load(f)
    except Exception as e:
        print(f"Error loading YAML file {filepath}: {e}")
        sys.exit(1)

def validate_new_alert(new_alert, valid_alert_keys, force):
    """
    Check if every key in new_alert is in valid_alert_keys.
    Return a list of invalid keys (if any).
    """
    invalid = []
    for key in new_alert.keys():
        if key not in valid_alert_keys:
            invalid.append(key)
    if invalid and not force:
        return invalid
    return []

def update_rule_append(rule_data, new_alert):
    """
    Append mode: For each key in new_alert, update its value in rule_data.
    If the key does not exist in rule_data, add it.
    """
    for key, value in new_alert.items():
        rule_data[key] = value
    return rule_data

def update_rule_override(rule_data, valid_alert_keys, new_alert):
    """
    Override mode: Remove all keys in rule_data that are present in valid_alert_keys,
    then add all keys from new_alert.
    """
    for key in list(rule_data.keys()):
        if key in valid_alert_keys:
            del rule_data[key]
    for key, value in new_alert.items():
        rule_data[key] = value
    return rule_data

def process_file(input_path, new_alert, valid_alert_keys, mode, force, yaml_instance, output_path):
    rule_data = load_yaml(input_path, yaml_instance)

    # Validate new alert section keys:
    invalid_keys = validate_new_alert(new_alert, valid_alert_keys, force)
    if invalid_keys:
        print(f"Error: The following keys in the new alert section are not valid alert fields: {invalid_keys}")
        sys.exit(1)
    
    if mode == "append":
        updated_rule = update_rule_append(rule_data, new_alert)
    elif mode == "override":
        updated_rule = update_rule_override(rule_data, valid_alert_keys, new_alert)
    else:
        print(f"Unknown mode: {mode}")
        sys.exit(1)
    
    with open(output_path, "w") as f:
        yaml_instance.dump(updated_rule, f)
    print(f"Updated rule written to {output_path}")

def process_directory(input_dir, new_alert, valid_alert_keys, mode, force, yaml_instance, output_dir):
    """
    Recursively process all YAML files (.yml or .yaml) in a directory.
    """
    for root, _, files in os.walk(input_dir):
        for file in files:
            if file.endswith(".yml") or file.endswith(".yaml"):
                input_path = os.path.join(root, file)
                rel_path = os.path.relpath(input_path, input_dir)
                output_path = os.path.join(output_dir, rel_path)
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                process_file(input_path, new_alert, valid_alert_keys, mode, force, yaml_instance, output_path)

def main():
    parser = argparse.ArgumentParser(description="Modify the alert section of ElastAlert rule YAML file(s).")
    parser.add_argument("--input", required=True, help="Input ElastAlert rule YAML file or directory")
    parser.add_argument("--alertfile", required=True, help="YAML file with the new alert section")
    parser.add_argument("--validfile", required=True, help="YAML file with the valid alert fields dictionary")
    parser.add_argument("--mode", choices=["append", "override"], required=True,
                        help="Mode: 'append' to update matching keys; 'override' to replace the alert section")
    parser.add_argument("--force", action="store_true", help="Force update even if invalid keys are found")
    parser.add_argument("--output", required=True, help="Output file or directory for the updated rule(s)")
    
    args = parser.parse_args()

    yaml_instance = YAML(typ="rt")
    yaml_instance.default_flow_style = False

    # Load the new alert section from the provided alertfile.
    new_alert = load_yaml(args.alertfile, yaml_instance)
    # Load the valid alert fields dictionary and extract its keys as a set.
    valid_alert_dict = load_yaml(args.validfile, yaml_instance)
    valid_alert_keys = set(valid_alert_dict.keys())

    # Determine if --input is a file or a directory
    if os.path.isfile(args.input):
        if os.path.isdir(args.output):
            output_path = os.path.join(args.output, os.path.basename(args.input))
        else:
            output_path = args.output
        process_file(args.input, new_alert, valid_alert_keys, args.mode, args.force, yaml_instance, output_path)
    elif os.path.isdir(args.input):
        if not os.path.exists(args.output):
            os.makedirs(args.output, exist_ok=True)
        process_directory(args.input, new_alert, valid_alert_keys, args.mode, args.force, yaml_instance, args.output)
    else:
        print("Error: --input must be a file or directory")
        sys.exit(1)

if __name__ == "__main__":
    main()

