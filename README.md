# AngebotFinder DE

This learning project collects offer candidates from eight German supermarkets and saves them to JSON.

```text
scripts/
  fetch_offers.py               Fetch, parse, and save offers
notebooks/
  02_shop_extraction.ipynb      Run the same fetching code interactively
data/
  processed/offers_dataset.json Saved offers and source statuses
  samples/                      Example data
tests/                          Offline checks for fetching and export
```

Use the project's Python environment. For a new environment, install the dependencies with `python -m pip install -r requirements.txt`.

The script defaults to `FETCH_DATA = False`. To refresh the JSON, set it to `True` near the top of the script and run this from the project folder.

```sh
python scripts/fetch_offers.py
```

Set the flag back to `False` after the refresh.

Run the extraction checks offline with `python -m unittest discover -s tests`.
