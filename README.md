# Teen Inflation Calculator (Singapore)

`index.html` is the whole website. The CPI data sits inside it between `/*DATA*/` and `/*END*/`.
`update.py` refreshes that data from SingStat (table M213751). `.github/workflows/update.yml` runs it every month.

## One-time setup
1. Create a GitHub account, then a new public repository called `teen-inflation`.
2. Upload these files, keeping the `.github/workflows/update.yml` path.
3. Settings > Pages > Source: "Deploy from a branch", branch `main`, folder `/ (root)`. Your site appears at `https://<username>.github.io/teen-inflation/`.
4. Settings > Actions > General > Workflow permissions: "Read and write permissions".
5. Actions tab > "Monthly CPI update" > Run workflow. Read the log.

## If the run fails
The script stops without changing the page and says why. Copy the message into Claude to fix it.
It was tested on mock data, not against the live API.

## Changing the basket
Edit the default amounts in the `defs` list near the bottom of `index.html`.
