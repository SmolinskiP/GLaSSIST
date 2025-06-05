# AGENT Instructions

This file contains guidelines for automated contributions to the GLaSSIST repository.

## Code Style
- Target Python 3.8 or newer.
- Use 4 spaces for indentation.
- Keep lines under 100 characters when possible.
- Include docstrings for all modules, classes and functions.
- Add type hints where they improve clarity.

## Commit Messages
- Start with a short summary line in imperative mood (max 72 characters).
- Optionally add a blank line followed by a more detailed description.
- Use English for all commit messages.

## Pull Requests
- Provide a concise title and describe key changes in a "Summary" section.
- Include a "Testing" section that lists commands run and their results.
- Add a "Notes" section if important context is needed.

## Testing
- The project does not yet contain automated tests.
- Validate Python files with:
  `python -m py_compile $(git ls-files '*.py')`
- If an automated test suite is added, run `pytest` before committing.

