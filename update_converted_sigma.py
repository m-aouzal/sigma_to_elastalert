#!/usr/bin/env python3
"""
This script updates converted ElastAlert rule YAML files (from Sigma conversion)
by retrieving the corresponding original Sigma rule (from a given sigma rules directory)
and extracting custom MITRE fields as follows:

  - mitre_attack_tactic: A list containing tags that start with "attack." (after removing the prefix)
      where the remaining text does NOT contain any digits.
  - mitre_attack_technique: A list containing tags that either:
        a) start with "attack." (after removing the prefix) and contain a digit,
        b) or do not start with "attack." at all.
  - risk: Taken from the sigma rule's "level" field (or a default if missing).

The updated fields are injected into the converted ElastAlert rule YAML file.
The script uses ruamel.yaml in round-trip mode to better handle complex formatting.
Note: This script does not modify any alert-related fields (such as alert_text), which
you plan to handle separately.

Usage:
    python update_converted_sigma.py --converted_dir ./converted_sigma_rules_to_elastalert \
         --sigma_dir ./sigma/rules/windows/ --output_dir ./final_rules --default_risk Medium
"""

import os
import argparse
import re
from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import PreservedScalarString

def load_yaml_file(filepath, yaml_parser):
    with open(filepath, 'r') as f:
        return yaml_parser.load(f)

def extract_mitre_fields_and_risk(sigma_rule_path, default_risk="Medium"):
    """
    Load the original sigma rule YAML and extract its tags and level.
    Splits the tags into two lists as follows:
      - tactics: for tags that start with "attack." (case-insensitive) where, after removing the prefix,
                 the remaining string does NOT contain any digits.
      - techniques: for tags that either:
           a) start with "attack." and, after removing the prefix, contain a digit, OR
           b) do not start with "attack." at all.
    Returns a tuple: (tactics, techniques, risk)
    """
    yaml_parser = YAML(typ='rt')
    try:
        sigma = load_yaml_file(sigma_rule_path, yaml_parser)
    except Exception as e:
        print(f"Error loading sigma rule file {sigma_rule_path}: {e}")
        return [], [], default_risk

    tags = sigma.get('tags', [])
    tactics = []
    techniques = []
    for tag in tags:
        # Ensure tag is a string and strip whitespace.
        if not isinstance(tag, str):
            continue
        tag = tag.strip()
        if not tag:
            continue
        # Check if the tag starts with "attack."
        if tag.lower().startswith("attack."):
            # Remove the prefix
            value = tag[len("attack."):].strip()
            # If the remaining text does NOT contain any digits, consider it a tactic.
            if not re.search(r'\d', value):
                tactics.append(value)
            else:
                techniques.append(value)
        else:
            # If tag does not start with "attack.", add it to techniques.
            techniques.append(tag)
    # Get the risk from the sigma rule's "level" field, or default.
    risk = sigma.get("level", default_risk)
    return tactics, techniques, risk

def update_converted_rule(converted_rule_path, sigma_rule_path, default_risk="Medium"):
    """
    Load the converted ElastAlert rule YAML file (using ruamel.yaml in round-trip mode),
    update it with custom fields extracted from the corresponding original sigma rule file,
    and return the updated rule data.
    Injected fields:
      - mitre_attack_tactic: list of tactic tags
      - mitre_attack_technique: list of technique tags
      - risk: sigma rule's "level" value (or default)
    """
    yaml_parser = YAML(typ='rt')
    try:
        converted_rule = load_yaml_file(converted_rule_path, yaml_parser)
    except Exception as e:
        print(f"Error loading converted rule {converted_rule_path}: {e}")
        return None

    tactics, techniques, risk = extract_mitre_fields_and_risk(sigma_rule_path, default_risk)
    converted_rule['mitre_attack_tactic'] = tactics
    converted_rule['mitre_attack_technique'] = techniques
    converted_rule['risk'] = risk

    # Optionally, ensure the description remains block styled.
    if 'description' in converted_rule:
        text = converted_rule['description']
        if not isinstance(text, PreservedScalarString):
            converted_rule['description'] = PreservedScalarString(text)

    return converted_rule

def process_all_rules(converted_dir, sigma_dir, output_dir, default_risk="Medium"):
    """
    Traverse the directory containing converted ElastAlert rule YAML files.
    For each file, find the corresponding original Sigma rule (by using the same relative path),
    update the converted rule with MITRE fields and risk, and write the updated YAML file
    to the specified output directory, preserving the relative path structure.
    """
    yaml_parser = YAML(typ='rt')
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    for root, _, files in os.walk(converted_dir):
        for file in files:
            if file.endswith(".yml") or file.endswith(".yaml"):
                converted_path = os.path.join(root, file)
                rel_path = os.path.relpath(converted_path, converted_dir)
                sigma_path = os.path.join(sigma_dir, rel_path)
                if not os.path.exists(sigma_path):
                    print(f"Warning: Original sigma rule not found for {converted_path}")
                    continue
                updated_rule = update_converted_rule(converted_path, sigma_path, default_risk)
                if updated_rule is None:
                    continue
                output_path = os.path.join(output_dir, rel_path)
                output_dir_for_file = os.path.dirname(output_path)
                if not os.path.exists(output_dir_for_file):
                    os.makedirs(output_dir_for_file)
                with open(output_path, 'w') as outf:
                    yaml_parser.dump(updated_rule, outf)
                print(f"Updated rule written to {output_path}")

def main():
    parser = argparse.ArgumentParser(
        description="Update converted ElastAlert rule YAML files with custom MITRE fields extracted from original Sigma rules."
    )
    parser.add_argument("--converted_dir", required=True,
                        help="Directory with converted ElastAlert rule YAML files")
    parser.add_argument("--sigma_dir", required=True,
                        help="Directory with original Sigma rule YAML files")
    parser.add_argument("--output_dir", required=True,
                        help="Directory to write updated ElastAlert rule YAML files")
    parser.add_argument("--default_risk", default="Medium",
                        help="Default risk value if 'level' is not present in the sigma rule (default: 'Medium')")
    args = parser.parse_args()

    process_all_rules(args.converted_dir, args.sigma_dir, args.output_dir, args.default_risk)

if __name__ == "__main__":
    main()

