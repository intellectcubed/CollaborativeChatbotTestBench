# Collaborative Domain

The Collaborative is made up of five neighboring rescue squads that provide 911 Emergency Medical Services to the community. Because squads struggle to staff an ambulance 24 hours a day, 7 days a week, they pooled their resources. On night and weekend shifts, the Collaborative covers the five squads' territories with fewer than five trucks, saving resources while still providing robust coverage.

On the radio, the Collaborative is called "Station 95." Colloquially, it is still referred to as "The Collaborative."

## Squads and Territories

Squads are volunteer or paid.  Volunteer squads offer their services free of charge, while paid squads bill their clients.  This usually has no bearing on scheduling, however, and is mentioned here only for completeness.

Each squad has a number and a home territory that uses the same number. Members usually refer to a squad by its number, but sometimes by its name.

| Squad / Territory | Name |
|---|---|
| 34 | Green Knoll |
| 35 | Finderne |
| 42 | Manville |
| 43 | Martinsville |
| 54 | Somerville |

A roster defines which members belong to which squad. Any member may request a schedule change for their own squad.

## Crews and Trucks

A squad that is on duty for a shift provides one crew and one truck. The terms *crew*, *truck*, and *squad on duty* are used loosely and interchangeably in conversation. In this document, "a squad is on duty" means that squad has a crew staffing a truck for the Collaborative.

Between **0 and 4** squads can be on duty for a given shift. **Two is typical.**

- **0 squads on duty** means the Collaborative has no coverage at all. This is an emergency: every call must go to mutual aid.

**Crew Roles**
Members can serve in the following roles.  Note that to be a Driver, the member must be an adult with a valid license and be certified to drive an emergency vehicle.  An EMT is a license granted by the state.  A Crew Chief is an experienced EMT.  Roles are listed below in their hierarchy from lowest to highest, members can always play roles that are less, but cannot serve in a higher role unless designated to do so.


1. Cadet (An under aged student.  They can be an EMT or not, or presently attending EMT training)
2. Assistant (Adult) - A person who is not certified to drive and not an EMT
3. Driver - Certified to drive (certification can be "loose" in that they can just be certified by the judgement of a squad)
4. EMT - Passed the state or national EMT test and keeps up with their training
5. Crew Chief - An experienced EMT who serves as the leader of the crew.

**A note on Crews** At a minimum, crews consist of 2 people and can be up to 4 people.  At least one of those 2 needs to be an EMT, the other can be just a "driver".  Typically, when talking about shifts and scheduling, if a crew does not have the minimum amount of members, it is not viable (Note: Paid squads need at least 2 EMTs.  Volunteer squads need at least 1 EMT and 1 Driver).  Therefore, if a member says "We are down 1 EMT for tonight" or "We are down 1 driver" they are implying that they do not have enough members to complete a crew (or not enough of the required roles).  They typically would not say that if there were supposed to be 3 members on duty, but now only 2 since those 2 might be the right mix to make a complete crew.

## Territory Coverage

Every territory is always assigned to exactly one on-duty squad's truck. A truck that is assigned a territory is *first due* for it: when a call comes out in that territory, the assigned truck answers it. The assigned territories are shown explicitly on the calendar.

When a squad is on duty, it is normally first due for its own territory, but not always. For example, when squad 34 and squad 54 are on duty, squad 34 covers (34, 35) and squad 54 covers (42, 43, 54).

How territories are split is not decided case by case. A fixed set of rules defines the distribution for **each combination of on-duty squads**: one definition for squads 34 and 54, another for 35, 42, and 43, and so on. When the set of squads on duty changes, the territory assignments change according to the definition for the new combination. If only one squad is on duty, it covers all five territories ("All").

- If the assigned truck is already out on a call and a second call comes out in its territory, another on-duty Collaborative truck takes the call.
- If all trucks are out on calls and another call comes in, the County dispatcher requests help from a neighboring squad. This is known as *mutual aid*.

Collaborative trucks also respond to mutual aid requests from territories outside the Collaborative that are adjacent to the ones they cover, if they are available.

The original plan called for a minimum of three trucks (Truck A covering two territories, Truck B covering two, and Truck C covering one). This proved difficult to maintain, so the Collaborative dropped down to **two trucks covering five territories**.

## Shifts

The Collaborative staffs night shifts seven days a week and day shifts on Saturday and Sunday only. There is no Collaborative coverage during weekday daytime hours.

- **Day shift:** 0600–1800
- **Night shift:** 1800–0600

All times are Eastern Time.

## Tango (Shift Supervisor)

Each shift has a shift supervisor, called "Tango," who resolves ambiguous situations. For example, if all trucks are out on calls, one truck becomes available, and a mutual aid request comes in, Tango decides whether that truck should take the call. If the County dispatcher has a question about the availability of any Collaborative resource, they ask Tango.

In the early days, when three trucks were on duty, a member of the Collaborative played the role of Tango. To simplify, one of the crews on duty is now designated as Tango and acts as the shift supervisor. Tango is shown on the calendar for each shift.

Tango is assigned so that the duty is distributed evenly among the squads over time, by how often each squad has been Tango. If only one squad is on duty, that squad is Tango.

When a squad has a break in its shift, Tango is adjusted for the duration of the break and then returns to what it was. If the set of squads changes (for example, a squad is added or dropped for a whole shift), Tango is reassigned by frequency. Tango is changed explicitly only when someone asks for it.

## Shift Naming Convention

Members refer to a shift by the day on which it **starts**. For example, if a squad will have no crew between 0100 and 0200 during the shift that begins Wednesday at 1800, they might say:

> "We will not have a crew during the Wednesday night shift from 0100 to 0200."

or, more simply:

> "We won't have a crew Wednesday from 0100 to 0200."

Although 0100–0200 technically falls on Thursday, it belongs to the Wednesday shift.

On Saturday and Sunday, there are two shifts (day and night), so "Saturday" can mean either one or both. Members often rely on context rather than saying "day" or "night" explicitly.

## Calendar

The Collaborative maintains a common group calendar, implemented in Google Sheets. Every member has a link to it and uses it to look up coverage. To protect the calendar's integrity, all members have read-only access, and a single person, the **Calendar Administrator**, makes all shift changes. The Administrator can always override the calendar. Changes can be undone, and a log of changes is kept.

### Baseline schedule

Each squad tells the Administrator which shifts it will staff. The Administrator builds the baseline schedule from those responses. This happens outside the chatbot system; the chat only carries changes to the baseline.

### What the calendar shows

For each shift (or part of a shift), the calendar shows:

- the start and end time
- which squads are on duty (0 to 4)
- which territories each on-duty squad covers
- which on-duty squad is Tango

### Calendar entry format

A shift is one calendar entry unless it is changed partway through. The entry has up to four squad slots, separated by `|`; unused slots stay empty, which is why entries end in `||`. For example, if squad 34 covers territories 34 and 35, squad 54 covers territories 42, 43, and 54, squad 34 is Tango, and both squads are on duty for the whole night shift, the entry reads:

```
1800 - 0600 (Tango: 34) | 34 (34, 35) | 54 (42, 43, 54)||
```

### Partial-shift changes

When a change covers only part of a shift, the entry is **split** into several consecutive entries. A squad that was scheduled but will not have a crew is kept in the entry as "No Crew," rather than removed, so the calendar still shows it was originally scheduled. The remaining squads' territories and Tango are recalculated for that time slot.

For example, if squad 34 will not have a crew from 2200 to 0100, the entry above becomes:

```
1800 - 2200 (Tango: 34) | 34 (34, 35) | 54 (42, 43, 54)||
2200 - 0100 (Tango: 54) | 34 No Crew | 54 (All)||
0100 - 0600 (Tango: 34) | 34 (34, 35) | 54 (42, 43, 54)||
```

## GroupMe Chat

All members of the Collaborative are invited to a GroupMe chat. It is meant for all important Collaborative matters but is used mostly to announce shift changes. The Calendar Administrator monitors the chat and updates the calendar to reflect the messages.

For example, if someone from squad 54 says they will not have a crew on Wednesday, the Administrator marks squad 54 as "No Crew" for that shift. The territories are then reassigned among the squads still on duty.

Typical messages include:
- a squad will have no crew for all or part of a shift
- a squad will add a crew or pick up a shift
- squads swap shifts
- a previous announcement is cancelled or reversed
- a crew will arrive late or leave early
