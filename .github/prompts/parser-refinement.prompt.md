---
agent: agent
---
## Parser Refinements
The parser needs to be refined to additionally identify and extract the following elements from the user provided pob:
1. **Main Skill**: The main skill of the Path of Exile player character. Typically the main skill is the one that the user
primarily uses for combat. It usually is supported by up to 5 support gems.
2. **Item Mods**: In Path of Exile, equipment items can have up to 6 explicit modifiers, as well as up to 3 implicit modifiers. The parser should be able to identify and extract these item modifiers from the pob. The frontend should be updated to display the modifiers for alongside each equipment item.

### Success Criteria
Given the cws-witch.txt pob, the refined parser should be able to identify "Detonate Dead" as the main skill and extract all equipment item modifiers correctly. This should be verified in a e2e test.

### Agent Instructions
Think hard about how to implement this. Keep iterating until we have a passing e2e test with the cws-witch.txt pob that verifies the main skill and item modifiers are correctly extracted and displayed in the frontend.