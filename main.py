import sys
import subprocess
import os

current_dir = os.path.dirname(os.path.abspath(__file__))


def main():

    # Read the current directory for files ending with .z64
    files_in_current_directory = [
        item
        for item in os.listdir(".")
        if os.path.isfile(os.path.join(".", item)) and item.endswith(".z64")
    ]
    results = []
    for f in files_in_current_directory:
        print(f"Extracting from ROM file: {f}")
        # Pass --called-by-main so extract.py knows it's being run from this script
        cmd = [sys.executable, os.path.join(current_dir, "extract.py"), "--called-by-main", f]
        try:
            completed = subprocess.run(cmd, capture_output=True, text=True, check=True)
            if completed.stdout:
                sys.stdout.write(completed.stdout)
            if completed.stderr:
                sys.stderr.write(completed.stderr)
            results.append((f, completed.returncode))
        except KeyboardInterrupt:
            raise
        except subprocess.CalledProcessError as e:
            if e.stdout:
                sys.stdout.write(e.stdout)
            if e.stderr:
                sys.stderr.write(e.stderr)
            if e.stderr:
                sys.stderr.write(e.stderr)
            print(f"Error extracting {f}, continuing...\n")
            results.append((f, e.returncode))
            continue

    print("Finished extractions. Results:")
    for f, success in results:
        if success >= 100:
            print(f"SUCCESS: {f}")
        else:
            print(f"FAILURE: {f} {success}%")


if __name__ == "__main__":
    main()
