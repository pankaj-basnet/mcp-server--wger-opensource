# Changelog

Changes to the wger REST API itself are documented in the backend's release
notes. This file records important changes to *this package*.

## Unreleased

* `log_set` can attach a set to the plan it was performed from, via the new
  `routine_id`, `slot_entry_id` and `iteration` arguments. Logs written without
  them are freestanding: wger reads a routine's log view and its statistics
  through that link, so an unattached set is invisible there and in the apps
  that show a plan's progress.
* New tool `get_workout_for_date`: what a routine prescribes on a given date,
  one entry per planned set, with the exercise name and the ids `log_set`
  needs. Reading the same thing by walking days, slots, entries and configs
  costs dozens of requests.
* First release on PyPI: `pip install wger-mcp` / `uvx wger-mcp` instead of needing a git checkout.
