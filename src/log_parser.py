import json
import pandas as pd


def load_logs(path):
    records = []
    with open(path, 'r') as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    df = pd.DataFrame(records)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["total_tokens"] = df["prompt_tokens"] + df["completion_tokens"]
    return df
