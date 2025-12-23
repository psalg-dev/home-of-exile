---
agent: agent
---
Define the task to achieve, including specific requirements, constraints, and success criteria.

## Mission Statement
This application supports players of the ARPG "Path of Exile" in improving their characters, making more Endgame Content available to them.

### Requirements
A player must be able to import his Path of Exile character into the application so that tailored recommendations can be made.
For importing Path of Exile characters the application must support Path of Building Export Codes or poe.ninja links.
The application must be able to recommend items, skill gems, and passive skill tree changes to the user based on their current character.
The application must provide a user-friendly interface for players to interact with the recommendations and make informed decisions about their character development.

### Technical Requirements

The application is to be developed as a web application accessible via modern web browsers.
The application should leverage Spring AI (https://spring.io/ai) where applicable to enhance recommendation quality.
We want to avoid duplicating existing open-source codebases and instead build upon them where possible.

The frontend should be based on Vue.js.
The frontend should be tested using Cypress for end-to-end testing.

The backend should be based on Spring Boot.
The backend should be tested using JUnit and Mockito.

### Code Conventions
Avoid source code files longer than 200 lines. 
Modularize code into small, single-responsibility components or classes.
Follow standard naming conventions for variables, functions, classes, and files.
Business logic must be covered by unit tests with at least 80% code coverage. 
Features must be covered by end-to-end tests.

### Constraints
The application must be developed using open-source technologies and frameworks.
The application must respect the terms of service of Path of Exile and any third-party services it interacts with.
The application must be designed to handle a large number of users and provide recommendations in a timely manner.

### Existing Codebases
There are existing community projects which support Path of Exile players:

#### Path of Building
Github Project: https://github.com/PathOfBuildingCommunity/PathOfBuilding
This application is the de-facto standard for Path of Exile character planning and simulation.
It is a desktop application written in Lua.

#### poe.ninja
Website: https://poe.ninja/
This website provides an overview of what builds are popular in the Path of Exile community and what items are currently worth.

### Success Criteria
The application successfully imports Path of Exile characters using Path of Building Export Codes or poe.ninja links.
The application successfully parses the imported character data and generates relevant recommendations for items, skill gems, and passive skill tree changes.
The application receives positive feedback from users regarding the usability and effectiveness of the recommendations provided.