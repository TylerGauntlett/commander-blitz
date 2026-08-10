# Backlog
- Controller support for Windows with XBox controller

# Features

## CPU Improvements

### Overview
- The AI had minmal training data and preforms very poorly
- This results in almost entirely random decisions that almost always lose the game without it being challenging
- Via this method, that app can offer difficulty levels for the CPU at the main menu that acutally influence the play style
- This is a uniquely hard problem as there are so many different ways to play MTG and variables involved
- Instead of trying to teach the model optimal play through pure machine learning, there is likely more deterministic the system could include at the various skill levels
- Basic concepts like blocking when safe to do so or attacking when safe to do so can be applied at the easiest levels
- From there, more complex decisions can be made to better stear the CPU into the correct choices based on the selected difficulty
- These could be written in the form of subagents writing persona documents for each supported difficulty
- These personas should document general strategies, expected behavior, etc
- This can then be turned into requirements and ultimately code

### Task
- Make the CPU opponents better at various levels using a combination of ML and deterministic conditoinals

<local-plans>\cpu-improvements-majestic-storm.md

---

## Variable Cost Cards

### Overview
- There are MTG cards that offer users multiple options for different costs
- There is currently no way to select which effect you'd like to trigger (example: Commanders Sphere)
- When playing/activating cards, users need to be able to trigger these
- There are also broad catagories of cards (ie kicker cost) that are flexible to how they should be used

### Task
- Add support for users to decide how they want to activate a card/which efffect to trigger. Consider using the existing attacking/defending/play panel on the right

## CI/CD to deply application

### Overview
- Using Github Actions, connect this repo with a cloud provider to enable continious delievery
- Ever new commit to main should start the build/deploy process
- A new droplet in digital ocean can be used to act as the server

### Task
- Build out CI/CD so all main branch commits produce a deployed version via Digital Ocean
