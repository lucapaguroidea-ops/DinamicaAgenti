# SAGA import agent

A program on the machine where SAGA C runs. It imports only (P5): pull the client's outbox, take
a backup label (`{cui}:{folder}:{utc}`), run SAGA's Import date in Nr.+data sync mode, send a
snapshot of what SAGA shows, and answer `wait_validare`. It never validates, devalidates, closes
a month or restores a backup. Until it is built, a person does these steps from the outbox.
SAGA's import format and user rights are quoted in `RESEARCH_LOG.md` R4 first (P16).
