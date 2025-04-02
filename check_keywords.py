import os
import re

directory = "./converted_rules_sigma_to_elastalert"

exemption_list = {
    "file.code_signature.valid", "host.containerized", "sysmon.file.archived", "sysmon.file.is_executable",
    "@timestamp", "event.created", "event.ingested", "winlog.event_data.ClientCreationTime",
    "winlog.event_data.DeviceTime", "winlog.event_data.NewTime", "winlog.event_data.OldTime",
    "winlog.event_data.PreviousTime", "winlog.event_data.ProcessCreationTime", "winlog.event_data.StartTime",
    "winlog.event_data.StopTime", "winlog.user_data.UTCStartTime", "destination.port", "event.sequence",
    "powershell.sequence", "powershell.total", "process.args_count", "process.parent.args_count",
    "process.parent.pid", "process.pid", "process.thread.id", "source.port", "winlog.process.pid",
    "winlog.process.thread.id", "winlog.record_id", "winlog.version", "log.offset"
}

def extract_fields_from_query(query_str):
    """
    Extract field names (words with dots) from the left side of colons in the query string.
    """
    # Pattern to match field names before a colon, optionally followed by .keyword
    field_pattern = r'\b\w+\.\w+(?:\.\w+)*(?:\.keyword)?(?=\s*:)'
    fields = set(re.findall(field_pattern, query_str))
    return fields

def process_yaml_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()
    
    # Find the query line directly (assumes 'query:' is at this nesting level)
    query_line = None
    lines = content.splitlines()
    for i, line in enumerate(lines):
        if 'query:' in line and 'query_string:' in lines[i-1]:  # Ensure it's under query_string
            query_line = line.strip()
            break
    
    if query_line:
        # Extract the query value (everything after 'query:')
        query_match = re.search(r'query:\s*(.+)', query_line)
        if query_match:
            query_str = query_match.group(1)
            fields = extract_fields_from_query(query_str)
            return fields, check_violations(fields, filepath)
        else:
            print(f"Warning: No query value found in {filepath}")
    else:
        print(f"Warning: No query line found in {filepath}")
    
    return set(), []

def check_violations(fields, filepath):
    violations = []
    for field in fields:
        if not field.endswith('.keyword') and field not in exemption_list:
            violations.append(field)
    return violations

def main():
    all_fields = set()
    files_with_violations = []

    print("Scanning .yml files for fields with dots...\n")
    for root, _, files in os.walk(directory):
        for filename in files:
            if filename.endswith('.yml'):
                filepath = os.path.join(root, filename)
                fields, violations = process_yaml_file(filepath)
                all_fields.update(fields)
                if violations:
                    files_with_violations.append((filepath, violations))

    # Print results to console
    print("Unique fields with dots found in queries:")
    for field in sorted(all_fields):
        print(f" - {field}")
    print(f"\nTotal unique fields: {len(all_fields)}")

    # Save results to violations.txt
    with open("violations.txt", "w") as f:
        f.write("Unique fields with dots found in queries:\n")
        for field in sorted(all_fields):
            f.write(f" - {field}\n")
        f.write(f"\nTotal unique fields: {len(all_fields)}\n")

        if files_with_violations:
            f.write("\nFiles with fields missing .keyword (non-exempted):\n")
            for filepath, violations in files_with_violations:
                f.write(f"\nFile: {filepath}\n")
                f.write("Violations:\n")
                for v in violations:
                    f.write(f" - {v}\n")
        else:
            f.write("\nNo violations found: All non-exempted fields have .keyword suffix.\n")

    # Print violations to console
    if files_with_violations:
        print("\nFiles with fields missing .keyword (non-exempted):")
        for filepath, violations in files_with_violations:
            print(f"\nFile: {filepath}")
            print("Violations:")
            for v in violations:
                print(f" - {v}")
    else:
        print("\nNo violations found: All non-exempted fields have .keyword suffix.")

if __name__ == "__main__":
    main()
