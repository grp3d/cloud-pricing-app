# New functionality

## User Creation and Administration, Introduction of tabs
(* To demo this application and "show value", I need to have "pre-built" architectures. To do this, we need to move away from client browser persistence to backend persistance. Here's the functionality needed:
* We now need the ability to create users. To do this, the site now needs multiple tabs. Tab 1: Cloud Pricing (active tab on page load), Tab 2: Trends (not part of this effort, tab can be shown but should be grayed out / lack functionality), Tab 3: Admin (will only show if user is an admin user)
*  User creation and authentication: 
   > For this version, users need to be created by the admin in the admin tab. The admin tab will contain a table that look as follows:
   Users     |     Active   |    Password               |    Purge
   ---------------------------------------------------------------------
   User X    |     [ ]     |      xyz  [Update Button]  |  [ remove user ]  
   User Y    |     [ ]     |      abc  [Create Button]  |  [ remove user ] 
  
   [ Create New User ]

   where: 
   - The users column shows the existing usernames in the system
   - Active column is a checkbox that (i) defaults to true on creation (ii) allows the admin to deactivate so this user cannot use the site (but all data remains) 
   - The Password column shows the last 4 characters of the hash (if one exists). If the user has a defined password, there should be an update button for the admin to change the password (via popup). If the user does not have a password, there should be a create button to define one (via popup)
   - The purge column contains a button that purges the user and all associated data/architectures from the system - only the selected user's row is deleted - admin confirmation is requried before proceeding with the deletion (this action should ONLY purge 1 user from the system)
   - The Create New User button below the table should create a new row in the table - only the username column is a required field for creation. 

   > The top left corner of the screen should have a small icon of a person (see /Users/ghubs/Development/repos/personal/cloud-pricing/screenshot-samples/user_icon.png ). If no user has been selected, the user will default to 'guest'. Guest mode behaves as the site does today - they can use the site, but persistence will remain in the browser. On click of the user icon the user will see either see:
    Guest
    [ login ]
 if they are not logged in or 
    Username
    [ change user ]
 if they are logged in

   > On click of login, there will be a pop up for the user to enter their username. If that user exists and there is no password, they must create a password. If the password exists, they must enter their correct password. For this version, an ecrypted password will be stored in the users table of the db (in later versions we will introduce better security via a system like Supabase). For now, it's sufficient to store the encrypted user entered password and subsequent attempts will compare the encrypted user entered value with the encrypted value stored in the db. If the user enters a user that does not exist or a password that is incorrect the popup with close and they will remain in guest mode.

* A default Admin user will be created on inititalization. This user will have a default password of admin123. This user cannot be deactivated via the checkbox in column 2 of the user table and the remove user button should be disabled for this special row

## Column 1 Updates to support Architecture imports 

*  To the right of AWS Architectures text, add an Import button. On click, the import button will list pre-defined architectures available to everyone. The pre-defined architectures are grouped by the owning username (username appearance is also sorted, but the Admin user should be at the top). Within each username group, the list of architectures is sorted by name. If a user has no architectures to share, then they will not show up in the dropdown  e.g.:
Username X
--------
archX
archY
...
Username Y
archZ
...


* On the selection of an architure from the import dropdown, the user will be prompted to name it and the default name in the prompt will be 'My Xxx' where Xxx is the name of the shared architecture.
Users.

## Column 1 Updates to support Architecture sharing 

* The current list of architectures in column one contains an X on each line item to delete the architecture. To the right of this x, we will add a icon to make the architecture "public" so other users an import it. This icon can be found here: /Users/ghubs/Development/repos/personal/cloud-pricing/screenshot-samples/make_public_icon_2.png. 
*  By default, architectures are not public / available for other users to load via import. When the architecture is not public, the icon will have no border. When the architecture is public, the icon will have a green border.
*  When the the architecture is not public (there is no border), mousing over the icon will show the text 'Click to make public'
*  When the the architecture is public (there is a border), mousing over the icon will show the text 'Click to make private'


## Other Column 1 updates
* The x in column 1 for deleted architectures should be red. On mousing over, the text should read 'Click to remove'
*  Move the Create architecture button and entry form in column 1 to be under the AWS Architectures text (if there are no architectures yet) or below the last architecture 

