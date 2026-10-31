# Shorelio launch checklist (owner actions only)

Code, config, tests and the production build path are done. These steps need
you.

## 1. Corrections email

Done: `contact_email` is `hello@shorelio.com`.

## 2. Default branch

The repo's only branch, and current default, is
`claude/determined-mccarthy-ctlz3b`. Recommended:

1. Create `main` from it:

   ```bash
   git push origin claude/determined-mccarthy-ctlz3b:main
   ```

2. Set **Settings → General → Default branch = `main`**.

Scheduled runs only happen on the default branch. Pushes and merges to
`main` also deploy automatically (once `MVP_PRODUCTION=true`); pushes to
Claude/development branches never deploy.

## 3. GitHub settings

1. **Settings → Pages → Build and deployment → Source: GitHub Actions.**
2. **Settings → Pages → Custom domain:** `shorelio.com`, then **Save**.
3. **Settings → Environments → github-pages → Deployment branches:** make
   sure your default branch (`main`) is allowed.
4. **Settings → Secrets and variables → Actions → Variables:** add
   `MVP_PRODUCTION` = `true`.
5. **Write permissions:**
   - The workflow declares its own job permissions (`contents: write` for
     data commits; `pages: write` and `id-token: write` for deploy), so the
     repo default can stay read-only.
   - If you add branch protection on `main` that requires pull requests,
     allow GitHub Actions to bypass it. Otherwise data commits are skipped;
     this is non-fatal, but last-known data then goes un-persisted.
6. Recommended: **Account Settings → Pages → Add a verified domain**
   (`shorelio.com`). Add the TXT record GitHub shows you, to prevent domain
   takeover.

## 4. DNS at your registrar

Apex `shorelio.com`, values from GitHub's custom-domain docs:

- **A records:** `185.199.108.153`, `185.199.109.153`, `185.199.110.153`,
  `185.199.111.153`.
- **AAAA records (optional, IPv6):** `2606:50c0:8000::153`,
  `2606:50c0:8001::153`, `2606:50c0:8002::153`, `2606:50c0:8003::153`.

`www.shorelio.com`:

- **CNAME** → your GitHub Pages default domain, i.e. the `<owner>.github.io`
  name shown in Settings → Pages. Use the owner name only, no repo name.

Also:

- Remove any parking/default A records your registrar added.
- **Do not create wildcard (`*`) records.**

## 5. HTTPS

After DNS resolves, which can take up to 24 h, tick **Settings → Pages →
Enforce HTTPS**.

## 6. First production run

1. **Actions → mvp-site → Run workflow** on `main`.
2. In the log, check:
   - tests `OK`;
   - the build line shows `stale: none`;
   - "Deploy gate" says `deployable=true`;
   - the deploy job succeeds.

## 7. Verify the live site

1. Open `https://shorelio.com/data-quality/`. Check the source timestamps are
   fresh, with no STALE labels, and review any open items.
2. On your phone, check the trip finder, one lake page and `/recently-stocked/`.
3. Check `https://shorelio.com/robots.txt` shows `Allow: /` plus the sitemap
   line.
4. View a page's source and confirm it has **no** `noindex`.

## 8. Search Console

1. Add a **Domain property** for `shorelio.com`, verified by a DNS TXT
   record. The alternative is a URL-prefix property using
   `google_site_verification` in config.
2. Submit `https://shorelio.com/sitemap.xml`.
3. Use URL Inspection on `/`, `/recently-stocked/` and two lake pages, then
   **Request indexing**.

## 9. Afterwards

Once the one-week Step 1 monitor reports completion, disable the scheduled
task "WDFW stocking daily monitor (1 week)". Note that it commits snapshots
to `claude/determined-mccarthy-ctlz3b`.
