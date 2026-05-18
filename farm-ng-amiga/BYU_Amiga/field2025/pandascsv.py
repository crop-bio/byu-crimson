import pandas as pd
from pathlib import Path

def create_and_save_csv(data, filename, columns=None, folder=None, index=False):
    """
    Create and save a CSV file using pandas.

    Parameters
    ----------
    data : list of lists or list of dicts
        The data to save. Example:
            [[1, "Alice", 25], [2, "Bob", 30]]
        or
            [{"id": 1, "name": "Alice", "age": 25}, {"id": 2, "name": "Bob", "age": 30}]
    filename : str
        The name of the CSV file (with or without .csv extension).
    columns : list of str, optional
        Column names (required if `data` is a list of lists).
    folder : str or Path, optional
        Folder to save the CSV in. If None, saves in current directory.
    index : bool, default False
        Whether to include the index column in the CSV.

    Returns
    -------
    Path
        The full path to the saved CSV file.
    """

    # Ensure .csv extension
    if not filename.endswith(".csv"):
        filename += ".csv"

    # Handle folder path
    folder_path = Path(folder) if folder else Path.cwd()
    folder_path.mkdir(parents=True, exist_ok=True)

    # Create DataFrame
    if isinstance(data, list) and len(data) > 0:
        if isinstance(data[0], dict):
            df = pd.DataFrame(data)
        else:
            df = pd.DataFrame(data, columns=columns)
    else:
        df = pd.DataFrame(columns=columns)

    # Save to CSV
    save_path = folder_path / filename
    df.to_csv(save_path, index=index)

    print(f"✅ CSV saved to: {save_path.resolve()}")
    return save_path


def save_csv():
    # create csv 
        # naming: by datetime?
    # create dataframe
    pass

maindf = pd.DataFrame(columns=["latitude", "longitude"])
data = dict(zip(["latitude", "longitude"], [[3.6], [-10]]))
df = pd.DataFrame(data)
# print(df)
df2 = pd.DataFrame(data)
# print(df2)
maindf = pd.concat([maindf, df2])
maindf = pd.concat([maindf, df2])


newdf = pd.read_csv('outputfile.csv')
print(newdf)