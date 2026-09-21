# Hongguo Python batch downloader

Command-line and desktop clients for downloading authorized Hongguo short-drama
episodes through the service API. Bulk downloads require a valid license/API key;
the tool does not bypass service limits.

## Modern PyQt6 desktop UI

```powershell
python main.py
```

The desktop interface includes a live public-catalogue search, selectable drama
results, a local queue, and preferences. Download actions remain disabled until
an authorized endpoint is configured.

## Offline application activation

Create the signing keys once on the Admin computer:

```powershell
python activate.py init
```

Keep `activation_keys/license_private_key.pem` private and back it up. The public
key in `resources/license_public_key.pem` is bundled with the application.

When a user opens the tool for the first time, they copy the displayed Machine
ID and send it to the Admin. For interactive use, run this and paste the Machine
ID when prompted:

```powershell
python activate.py
```

The equivalent one-line command is:

```powershell
python activate.py generate USER_MACHINE_ID
```

Send the single generated code back to the user. It works only on the computer
whose Machine ID was supplied. Telegram and a web activation server are not used.

## Setup (Windows PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:HONGGUO_KEY = "在这里填团队提供的真实Key"
$env:HONGGUO_API_BASE_URL = "https://在这里填团队提供的真实API地址"
```

Values such as `YOUR_KEY`, `CURRENT_API_URL`, `BOOK_ID_1`, and `BOOK_ID_2` are
placeholders only. They will not work as literal command values.

The key can alternatively be saved with `python cli.py config --key YOUR_KEY`, but
the environment variable is recommended because it is not written to disk.

The API URL bundled in the older public Python repository currently returns 404.
Set `HONGGUO_API_BASE_URL` to the current endpoint supplied by the Hongguo
Downloader team. If they supply a separate preview endpoint, set
`HONGGUO_PREVIEW_URL` as well. Do not extract private endpoints from the Windows
binary; request the supported API contract from the team.

## Find a drama

```powershell
python cli.py search "剧名"
python cli.py episodes BOOK_ID
```

`search` reads the public catalogue pages on `hongguoduanju.com`; it does not
need the old private API. The catalogue parser is adapted from the
MIT-licensed `lingbol088-spec/short-drama-downloader` GitHub project. Resolving
episodes and video URLs still requires a supported, authorized API endpoint.

## Download one drama

```powershell
python cli.py download BOOK_ID --episodes all --quality 1080P+ --concurrent 4
```

## Download many dramas

Pass several IDs directly:

```powershell
python cli.py batch BOOK_ID_1 BOOK_ID_2 BOOK_ID_3 --concurrent 4
```

Or create a UTF-8 queue file named `batch.txt` in the project folder first:

```text
# book_id|optional title|episodes
123456|My first drama|all
789012|My second drama|1-20,25
345678||all
```

Then run:

```powershell
python cli.py batch --file batch.txt --quality 1080P+ --dir D:\Hongguo
```

Completed episode files are skipped, so rerunning the same command resumes the
queue without downloading those files again. Concurrency is limited to 1-10
episodes per drama to avoid overwhelming the service.

## Publishing an update

Pushing commits to `main` does not publish an application update. The in-app
updater reads the latest published GitHub Release. Update `APP_VERSION` in
`version.py`, commit and push the changes, then create and push a matching tag:

```powershell
git tag v1.1.3
git push origin v1.1.3
```

The `Release Windows` GitHub Actions workflow builds and publishes
`DeepXII-Tools-Setup.exe` together with its SHA-256 checksum. Existing builds
will then detect the newer release from the **Update Tools** button.
