# Setting up OSMM — Open Source Makerspace Manager (plain-language guide)

This guide is for makerspace organisers who are **not** software developers. It walks you through
running OSMM on a computer at your space, step by step. You don't need to understand
the code — just follow along.

You'll need about **30 minutes** and one **always-on computer** (any spare PC, a Mini-PC, or an
Intel NUC) that stays on and connected to your network.

---

## Step 1 — Install Docker Desktop

Docker is the free "engine" that runs the app. Install it once:

1. Go to **https://www.docker.com/products/docker-desktop/**.
2. Download the version for your computer (Windows or Mac) and run the installer.
3. Click through the installer (the defaults are fine), then **start Docker Desktop** and wait
   until it says it's running (a whale icon appears in your taskbar/menu bar).

> If Docker asks you to enable virtualization/WSL on Windows, accept — it sets it up for you.

## Step 2 — Download the app

1. Open the project's GitHub page in a browser.
2. Click the green **Code** button → **Download ZIP**.
3. **Unzip** it somewhere easy to find, e.g. your Desktop. You'll get a folder like
   `Makerspace-Manager`.

## Step 3 — Run the setup

This is the only "command" you'll run, and the script does the rest (it makes all the passwords
and security keys for you).

**On Windows:**
1. Open the unzipped folder.
2. Right-click the file **`setup.ps1`** → **Run with PowerShell**.
   - If Windows blocks it, open **PowerShell** in that folder and run:
     `powershell -ExecutionPolicy Bypass -File setup.ps1`

**On Mac/Linux:**
1. Open the **Terminal** app.
2. Drag the folder onto the Terminal window to go into it (or type `cd ` then drag the folder),
   press Enter, then run:
   `bash setup.sh`

The script will ask you a few simple questions (press Enter to accept the suggestion in brackets):

| Question | What to type |
|---|---|
| Web address people will type | `localhost` to start (you can change it later) |
| Name of your makerspace | e.g. `Riverside Makerspace` |
| Admin login username | `admin` is fine |
| Admin email | your email |
| Admin password | type one, or leave blank and it makes a strong one for you |

Then it builds and starts everything. **The first time takes a few minutes** — that's normal.

## Step 4 — Open it

When the script finishes it prints two web addresses. Open them in a browser:

- **Public catalog** — what your community sees (browse + request).
- **Staff console** (`…/admin`) — the React console where Space Managers, Inventory Managers,
  Guest Admins, Print Managers, and the Super Admin do day-to-day work.

The Django control plane is at `/control/` on the backend only. It is an operator-only tool and is
not exposed on the public website/port.

**Write down the admin username and password it shows.** If you let it generate a password, that
line is the only time it's displayed.

## Step 5 — Make it useful

Log into the **staff console** address (`/admin`) and:

1. **Add your inventory** — the tools and equipment people can borrow.
2. **Turn on public visibility** — open your makerspace and enable **"public inventory"** so it
   shows on the public catalog.
3. **Add your team** — create accounts for your staff and assign them a role (Space Manager,
   Inventory Manager, Guest Admin, Print Manager). Your staff use this **staff console** for
   everything. (See the roles table in the [README](../README.md#roles--permissions) — the
   roles are fixed by the system; you only choose who gets which one.)
4. **(Optional) Email & Telegram alerts** — set your makerspace's email (SMTP) and Telegram bot in
   the staff console's **Integration settings**. These are stored encrypted and never shown again.

---

## Letting people on your network reach it

By default it's at `localhost` (only that computer). To let others at your space use it:

1. Find that computer's address on your network (its local IP, like `192.168.1.50`, or its
   hostname).
2. Re-run the setup once and enter that address when asked for the "web address", **or** edit the
   `ALLOWED_HOSTS` and `CORS_ALLOWED_ORIGINS` lines in the `.env` file to include it, then run
   `docker compose -f docker-compose.prod.yml -f docker-compose.build.yml up -d`.
3. People then visit `http://<that-address>/` in their browser.

> For a public website with a real domain and HTTPS, you'll want someone technical to put a
> reverse proxy (e.g. Caddy or Nginx with a certificate) in front and set `ENABLE_HTTPS=true`.
> See [self-hosting.md](self-hosting.md).

## No spare computer?

You have two good options before giving up:

1. **Partner with another makerspace.** This app can run **many makerspaces on one backend**. If a
   nearby makerspace already runs it on their server, ask them to add yours as another "tenant" —
   you'll get your own catalog, your own web address, and your own admin, all on their shared
   backend. Most makers are glad to help another space, and it's an easy way for them to contribute.
2. **Use a hosted database (Supabase).** If partnering isn't possible, you can host the app on a
   cloud platform and use a free **Supabase** Postgres database. This is more technical — see
   **Option C** in the [README](../README.md#hosting).

---

## Everyday operations

- **Start it / after a reboot:** Docker Desktop can auto-start the app, or run the same
  `docker compose … up -d` command.
- **Stop it:** `docker compose -f docker-compose.prod.yml -f docker-compose.build.yml down`
  (your data is safe — it's kept in a database volume).
- **Update to a newer version:** download the new ZIP over the folder and run the setup script
  again; your `.env` and data are preserved.

## Something went wrong?

- **"Docker is not running"** — open Docker Desktop and wait for it to start, then try again.
- **The page won't load** — give it another minute on first run; the build takes time.
- **See what's happening:** run
  `docker compose -f docker-compose.prod.yml -f docker-compose.build.yml logs backend`.
- Still stuck? Open an issue on GitHub describing what you did and what you saw.
