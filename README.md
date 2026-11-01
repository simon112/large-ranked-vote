# large-ranked-vote

A small self-hosted poll for ranking **lots** of options: dozens of candidate names, not a handful. People sort the options into tiers, refine the tiers, and the results are scored by Borda count, with other voting systems shown alongside for comparison.

There are no accounts. You make a poll, share the link, and each person votes under their name. The whole thing is one Python file using only the standard library, with SQLite for storage, plus two HTML pages.

## Why tiers

Dragging 60 options into a strict order is miserable. Here each option comes up as a card, and you put it in one of five tiers (*Love it*, *Like it*, *Fine*, *Meh*, *No*). Then you refine only as far as you care to:

- **⊟ Split** breaks a big tier into High / Mid / Low, asking about each option in turn. Splits can nest two levels deep.
- **⇅ Compare** orders a small group with "this or that?" questions.
- **Drag** by ⠿, or tap an option for move buttons.

Your ballot is the whole list read top to bottom. Tiers and splits only help you build it; scoring uses the flat order.

## Scoring

Borda count: with *n* options, your 1st choice gets *n*−1 points and your last gets 0. Results and everyone's individual rankings are shown on the poll page and refresh every 15 seconds.

Below the Borda results, collapsed panels count the same ballots by other methods, each showing its winner in the panel header:

- **First choices (plurality)**: only each voter's #1 counts.
- **Instant runoff**: the option with the fewest votes is knocked out round by round. Ties go against the lower Borda score.
- **Head-to-head (Copeland)**: options ranked by pairwise contests won, marking a Condorcet winner if there is one.
- **Schulze**: head-to-head, but a stronger chain of wins can outweigh a single defeat.
- **Approval**: how many voters put each option in *Love it* or *Like it*.

These are computed in the page from the ballots the API returns. Where they agree with Borda, the winner doesn't hinge on the counting method.

The starting order of the cards is shuffled per voter, so nobody's ranking inherits the order the options were entered in. For the same reason, link previews don't list option names.

## Votes and names

- A vote is keyed by name (case-insensitive) within a poll. Saving again under the same name replaces it.
- Unsaved work is kept as a draft in the browser, so a refresh puts back exactly what was on screen.
- **Load your vote** pulls a saved vote into a new browser or device to edit it.
- **Change name** and **Delete this vote** fix a vote saved under the wrong name. Delete asks first and shows when the vote was saved and its top choices.
- If a browser saved under one name and then saves under another, it asks whether to move the earlier vote or keep both, for people sharing a device.

There is no authentication: anyone with the link can overwrite, rename or delete any vote by name. It's meant for groups that trust each other, such as friends picking a name.

## Running it

Requires Python 3.9+ and nothing else.

```sh
python3 server.py            # http://127.0.0.1:8787
```

Environment variables:

| Variable    | Default           | Meaning                  |
|-------------|-------------------|--------------------------|
| `POLL_HOST` | `127.0.0.1`       | address to listen on     |
| `POLL_PORT` | `8787`            | port                     |
| `POLL_DB`   | `polls.db` beside `server.py` | SQLite file |

Polls are created at `/` and live at `/p/<id>`. The API is listed at the top of `server.py`.

## Deploying as a sandboxed service

`poll.service` is a systemd unit that runs the server as an unprivileged `poll` user under a tight sandbox. Its filesystem is an allowlist: the service's root is an empty directory, and only what the server was traced opening is mounted into it:

- the Python binary, its standard library and the system's shared libraries;
- the app in `/opt/poll`, read-only;
- its database directory, `/var/lib/poll`.

There is no `/etc`, `/home`, other binaries, or anything else on the host; `/proc`, `/sys` and the shared parts of `/dev` are empty.

The service has no network access of its own. `poll.socket` listens on `127.0.0.1:8787` and accepts only localhost peers, then passes the listening socket to the server (socket activation). The server can't create any socket, so it can't reach other services on the machine, even ones on localhost. It also has no capabilities, its system calls are filtered, and its memory, task and CPU use are capped. The unit pins `/usr/bin/python3.12` (Ubuntu 24.04); adjust the paths for another Python.

Put a reverse proxy or tunnel in front of it to make it public. `deploy.sh` copies the code to `/opt/poll`, installs both units and restarts the service. Run directly (`python3 server.py`), the server binds `POLL_HOST:POLL_PORT` itself.

```sh
sudo useradd --system --no-create-home --shell /usr/sbin/nologin poll   # once
./deploy.sh
```

The database lives at `/var/lib/poll/polls.db`.

## Limitations

- Options can't be changed after a poll is created, since that would invalidate ballots already cast.
- 2–200 options per poll; names up to 60 characters.
- SortableJS is loaded from jsDelivr for dragging.

## License

MIT. See [LICENSE](LICENSE).
