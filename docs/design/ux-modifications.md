# Chatbot Driver UI modifications
This document contains instructions how to refactor the UX for the testing driver application (Chatbot Testing Workbench).  Where possible, try to reuse existing code since I have already tested its functionality.

For this rewrite, we will remove the panel on the left, and make the tab area the full width of the screen.

**Keep the below rules in mind**
- Each tab should be in its own class
- Where possible create some utility classes for functions that are reused across tabs (or classes)

## Top of page
Put a banner at the top of the page that gives a description of the configuration.

- Title: Chatbot Testing Workbench
- Live Calendar checkbox
- Model usage panel:
  - **Chatbot tokens** in and out for this page session, added up from the token counts in the status answers
    (Bot tab replies and Batch tab rows), each message counted once. **Reset tokens** sets them to zero.
  - **Bot tokens** and the **budget**: the bot's own tester and judge models. Read when the page opens, when a bot
    run ends, and after Reset. The page does not poll `/api/usage`.

---

## Main part of page
Show tabs for each of the functions.  The below tabs will be displayed: 

## Tab: Batch
This tab allows us to load a batch file containing a log of the GroupMe messages. I can load a file containing messages and they will appear in the main part of the page in a scrollable window.  I can then filter, Run all or Run from the selected down.

The top part of this tab will contain a static portion, and a scrollable portion.  The static portion will be at the top, full width of the tab.  Below the static panel we will have a scrollable window that contains the messages.

### Static panel at the top of the tab area
#### Load file panel
Title: Batch File
Button: `Choose File`
Text (not editable): Name of file loaded (without the path)

Confirmation that the file was opened and show how many messages it contains

#### Filter panel
Title: Filter
On one line: `From`, From date control, `To:`, To date control
Buttons:
- `Filter`
- `Clear`
- 
#### Run Panel 
Title: Run
Buttons: 
- Run Selected
- Run All Checked
- 
#### Control Panel
Title: Control
Buttons: 
- `Pause`
- `Resume`
- `Stop`
- `Mark All Pending`

### Scrollable Message Area
Messages that were loaded and filtered will appear here.  This area occupies the full width of the page and is scrollable.  Messages are displayed as they currently are.  The highlights also remain the same with the runnable message in blue, running message in yellow.  Also, we have checkboxes that indicate messages to be run. 

## Tab Create 
Leave as is

## Tab: Bot
Leave as is
