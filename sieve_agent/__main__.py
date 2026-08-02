"""Entrypoints — installed as the `sieve_agent` command (and `python -m sieve_agent`):

  sieve_agent                       chat in the terminal (default)
  sieve_agent dashboard             the browser cockpit → localhost:7777 (+ Telegram if configured)
  sieve_agent voice                 talk to it (needs the [voice] extra)
  sieve_agent telegram              phone → laptop (needs TELEGRAM_BOT_TOKEN)
  sieve_agent discord               Discord → laptop (needs DISCORD_BOT_TOKEN)
  sieve_agent whatsapp              WhatsApp → laptop (needs WHATSAPP_TOKEN, public URL)
  sieve_agent brief                 morning briefing (calendar + mail + memory) — as a LOOP
  sieve_agent gather                same job as a GRAPH: github, web, calendar and
                             memory fetched together, then one digest
  sieve_agent skill install <url>   install a community skill
"""

from __future__ import annotations

import sys


def main() -> None:
    args = sys.argv[1:]
    if not args:
        from sieve_agent.gateway.cli import main as cli_main

        cli_main()
    elif args[0] == "dashboard":
        from sieve_agent.ops.dashboard import main as dash_main

        dash_main()
    elif args[0] == "voice":
        from sieve_agent.gateway.voice import main as voice_main

        voice_main()
    elif args[0] == "telegram":
        from sieve_agent.gateway.telegram import main as tg_main

        tg_main()
    elif args[0] == "discord":
        from sieve_agent.gateway.discord import main as discord_main

        discord_main()
    elif args[0] == "whatsapp":
        from sieve_agent.gateway.whatsapp import main as wa_main

        wa_main()
    elif args[0] == "brief":
        from sieve_agent.ops.brief import main as brief_main

        brief_main()
    elif args[0] == "gather":
        from sieve_agent.ops.gather import main as gather_main

        gather_main()
    elif args[0] == "skill" and len(args) >= 3 and args[1] == "install":
        from sieve_agent.memory.procedural.installer import install

        install(args[2])
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
