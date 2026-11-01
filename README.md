# large-ranked-vote

A small self-hosted poll for ranking **lots** of options: dozens of candidate names, not a handful. People sort the options into tiers, refine the tiers, and the results are scored by Borda count.

There are no accounts. You make a poll, share the link, and each person votes under their name. The whole thing is one Python file using only the standard library, with SQLite for storage, plus two HTML pages.

## Why tiers

Dragging 60 options into a strict order is miserable. Here each option comes up as a card, and you put it in one of five tiers (*Love it*, *Like it*, *Fine*, *Meh*, *No*). Then you refine only as far as you care to:

- **⊟ Split** breaks a big tier into High / Mid / Low, asking about each option in turn. Splits can nest two levels deep.
- **⇅ Compare** orders a small group with "this or that?" questions.
- **Drag** by ⠿, or tap an option for move buttons.

Your ballot is the whole list read top to bottom. Tiers and splits only help you build it; scoring uses the flat order.

## Scoring

Borda count: with *n* options, your 1st choice gets *n*−1 points and your last gets 0. Results and everyone's individual rankings are shown on the poll page and refresh every 15 seconds.

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

`poll.service` is a systemd unit that runs the server as an unprivileged `poll` user under a tight sandbox:

- the filesystem is read-only, with `/home` hidden;
- the network is limited to localhost;
- system calls are filtered;
- memory, task and CPU use are capped.

Put a reverse proxy or tunnel in front of it to make it public. `deploy.sh` copies the code to `/opt/poll`, installs the unit and restarts the service.

```sh
sudo useradd --system --no-create-home --shell /usr/sbin/nologin poll   # once
./deploy.sh
sudo systemctl enable poll                                              # once
```

The database lives at `/var/lib/poll/polls.db`.

## Limitations

- Options can't be changed after a poll is created, since that would invalidate ballots already cast.
- 2–200 options per poll; names up to 60 characters.
- SortableJS is loaded from jsDelivr for dragging.

## License

MIT. See [LICENSE](LICENSE).
