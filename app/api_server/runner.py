import json
import subprocess


class CommandError(RuntimeError):
    def __init__(self, command, returncode, stdout, stderr):
        self.command = command
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        super().__init__(self._message())

    def _message(self):
        return (
            f"Command failed with code {self.returncode}: {' '.join(self.command)}\n"
            f"STDOUT:\n{self.stdout}\n"
            f"STDERR:\n{self.stderr}"
        )


def run_command(command, cwd):
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 0:
        raise CommandError(
            command=command,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
    return completed.stdout


def extract_last_json_object(text):
    stripped = text.strip()
    start = stripped.find("{")

    while start != -1:
        candidate = stripped[start:].strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            start = stripped.find("{", start + 1)

    raise ValueError(f"No JSON object found in command output:\n{text}")


def run_json_command(command, cwd):
    stdout = run_command(command, cwd)
    return extract_last_json_object(stdout)


def run_streaming_command(command, cwd, on_output=None):
    process = subprocess.Popen(
        command,
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
    )

    chunks = []
    while True:
        chunk = process.stdout.read(1)
        if chunk == "" and process.poll() is not None:
            break
        if not chunk:
            continue
        chunks.append(chunk)
        if on_output:
            on_output(chunk)

    returncode = process.wait()
    output = "".join(chunks)
    if returncode != 0:
        raise CommandError(
            command=command,
            returncode=returncode,
            stdout=output,
            stderr="",
        )
    return output
