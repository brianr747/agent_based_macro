# agent_based_macro

##Simple Agent-Based Macro Model

This module now supports a very basic economic model. See my *space_trader* project for
a model implementation. Once I am satisfied with the first model, I will migrate it to this
project and set it up so that this project can be run by itself.

Until this project reaches some form of stability, updates (and initial documentation) will 
show up on my Patreon: https://www.patreon.com/brianromanchuk?fan_landing=true

##Overview

As the name suggests, this framework is used to implement agent-based macro models. The 
design includes agents that represent individual economic actors (mainly firms) as well as
agents that are in fact economic aggregates (such as the Household sector).

The design is aimed to support a client-server architecture, although the code currently runs 
inside a single process for simplicity during the initial design phase. It will take some
refactoring to add in client-server support.

The development plan was to build something as quick as possible that works, then switch to 
code cleanup. That initial build-out was completed, and now the objective is to clean up
code and keep it relatively clean as features are added.


