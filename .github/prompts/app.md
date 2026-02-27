## Home of Exile

Home of Exile is a Web Application for Players of the ARPG Path of Exile by Grinding Gear Games. 

Its main purpose is to support Player's character progression by recommending updates.
Its secondary purpose is to aggregate resources useful for players since those are quite scattered.

### Path of Exile
Path of Exile is an ARPG which still receives frequent Content Updates (every 4 - 6 months).
It has a 10+ years development history and thus offers the most complex character build system in any 
ARPG. That complexity poses a challenge to especially new players as they often are overwhelmed by
just the passive skill tree alone. 

#### Leagues
Path of Exile's seasonal content is called a "league". A league denominates a certain minimum patch
level of the game. For example the most recent league "Keepers of the Flame" was introduced
with update 3.27; Players tend to use version numbers any league names synonymously. 

#### Character Progression
Players start with a Level 1 character, gaining experience by killing monsters until they reach Level 100. 
As players progress through levels, they unlock access to increasingly powerful equipment and Skill and Skill-Support gems. 
Frequently swapping out gear to increase character power thus is a core activity that players perform
with decreasing frequency, the higher their character level gets. 

#### Resources
There are a lot of publicly available resources for Path of Exile. 

Authoritative Sources (among others):
- poewiki.net
- poedb.tw
- poe.ninja 

Community Projects on Github 
- RePoE
- Path of Building Community Fork 

### Main Purpose
The main purpose of this webapp is to support player's character progression by recommending updates. 
For this, users can share their Path of Building export with the webapp and have it parse
and analyze their character build. After analyzing the player's character build the app should
give 5 recommendations how the player can increase their character's power. 
This may include recommendations for equipment upgrades, reallocating passive skill tree points,
swapping out support gems etc. 

##### Recommendations
Recommendations must always be actionable to the player and take into consideration where on the 
progression path the player character currently is; i.e. any equipment upgrades must take into consideration
the character's attributes (str,dex,int), the level requirements of equipment upgrades etc. 

Since Path of Exile frequently receives content updates, recommendations which were valid for one 
league may not be so anymore in a following league. Also a new league may introduce new support gems, 
unique items etc which the application also must be able to take into consideration so recommendations
stay actionable when a new league starts. 

Players should be able to give thumbs up / down on whether a recommendation was helpful. This feedback should be incorporated so recommendations automatically improve over time. 

### Blacklist
Do not use the following resources:
- The Fandom PoE Wiki

 