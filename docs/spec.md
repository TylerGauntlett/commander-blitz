# Magic The Gathering Board State Engine

## Overview
- This is a engine that takes sequental Magic the Gather cards based on turn and play order to produce a board state
- It exclusively works for commander mode
- It takes a card or series of cards (in the case of resolutions) and produces a game state (ie player health, creatures, lands , etc)
- The system follows all rules of the standard commander game format
- The card effects (distinct from the obvious attack/toughness score) are intuperated with invalid combinations rejected
    - An example of this would be playing additoinal lands without having a creature/sorcery/instant/etc that specifically allowed these conditions
- This game engine is used by an AI system to train against each other on the best way to play a hand in MTG

## Mechanics
- The system is simple in that it only supports 2 decks
- Each deck is a valid commander deck from a recent generation (i.e. aesi tyrant of gyre strait /  edgar markov)
- It exposes an API to take in cards/sequences of cards and returns back a game state

## Technologies
- Language: Python

## Training
- A Python library is used to allow for machine learning of 2 competing systems in the game of magic the gathering
- It will run through 1000s of simulated duels against the 2 commander decks to understand card order, countering, game mechanics, etc
- The system must obey the rules of the game itself to win so keeping the rules engine seperate is important
- This training data should be segemented by player # as the number of players can influence how you play the game
    - An example would be a 1vs1 often means playing everything you can early while a 4-player mode might mean you hide your power level longer until you can reliably close out (else be the target of the others)

## Application
- From this system, I should be able to play an entire game of MTG against a reasonably compitent player
- This could take the form of a local react app with bun/biome
- It should follow all MTG rules (ie 7 cards to start, deck, graveyard, exile, commander, etc) in what is interactable
- Cards can be placed in a grid system
    - This system should have well spaced areas to drag cards into, broken up by types (lands, creatures, artifacts, enchantments, etc)
- An example of a system similar is Moxfield's play test mode

## Task
- Build the above system in the most MVP form
- Use unit tests as needed to prevent backsliding
- Generate documenation descibing all key aspects in user-readable detail (with diagrams)
- Verify core aspects of the engine and application work as expected before being considered compelete