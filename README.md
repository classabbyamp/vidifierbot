# VidifierBot

A telegram bot for getting videos from websites.

To use: [@vidifierbot](https://t.me/vidifierbot)

## Running

### Docker

1. Create a new directory and `cd` into it.

2. Create the `docker-compose.yml` file:

    ```yaml
    version: '3'
    services:
      bot:
        image: "ghcr.io/classabbyamp/vidifierbot:latest"
        restart: on-failure
        volumes:
          - "./data:/app/data:rw"
    ```

3. Create a subdirectory named `data`.

4. Copy the templates for `keys.py` and `help.md` to `data/`, and edit them.

5. Run `docker-compose`:

    ```none
    $ docker-compose pull
    $ docker-compose up -d
    ```

    > Run without "-d" to test the bot. (run in foreground)

## Copyright

Copyright (C) 2021-2022 classabbyamp

This program is released under the terms of the BSD-3-Clause license.
See `LICENSE` for full license text.

