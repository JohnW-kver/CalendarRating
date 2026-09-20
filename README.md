## Pitt Schedule Optimizer
A schedule builder for Pitt students that reads your plain-
English preferences, picks conflict-free course sections, and ranks them by what you actually care about
(e.g no classes at 8am, avoiding walking across campus between buildings, 
and sitting through long dead gaps between classes)

## Features
- Enter courses manually or import from a CSV/Excel file
- Describe your preferences in plain English
- Conflict-free schedule search across all section combinations
- Real walking-distance estimation between Pitt buildings (Haversine
  distance from actual building coordinates)
- Save schedules and export to `.ics` for Google Calendar

## Important Limitations
- Building walking times are estimated from straight-line coordinates plus
  a fixed overhead constant, not real routing, so it's only an estimate.
- CSV/Excel import expects the same 7-column format as the manual entry
  table (course, section, days, start, end, location, instructor).

## AI Tools Disclosure
**As a core feature:** NVIDIA Nemotron (via build.nvidia.com) powers the app's
natural-language course/preference parsing and the schedule comparison
explanations.

**As a development assistant:** Claude (Anthropic), Doubao, and GitHub Copilot was used throughout
development for debugging Gradio/API/git issues, 
drafting and reviewing the calendar rendering fix, the
Haversine-based walk-time calculation, the CSV/Excel import feature,
and the comparative schedule-scoring explanation function.

All AI-assisted code was reviewed, tested, and run by me before inclusion,
see `test_good.csv`, `test_bad.csv`, and `test_invalid.csv` for the test
cases I used to verify scoring behavior independently.
