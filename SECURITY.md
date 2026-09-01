# Security

Browser profiles under `data/profiles/` contain authenticated sessions. Treat
the entire `data/` directory and `.env` as secrets. Do not attach run HTML or
screenshots to public issues until you have inspected and redacted them.

Before publishing a fork, inspect ignored files and scan all tracked content:

```bash
git status --short --ignored
git grep -nEi 'sessionid|ds_user_id|c_user|li_at|NID_AUT|authorization:|cookie:'
```

Also search for your channel name, handles, email addresses, page IDs, campaign
names, sponsor names, and review codes. Rotate affected sessions immediately if
a browser profile or cookie is committed.

For a sensitive vulnerability, contact the repository owner privately rather
than posting credentials or account evidence in a public issue.
