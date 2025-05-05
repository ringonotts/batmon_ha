# batmon_ha
# Welcome to the BatMon Home Assistant Repo!

This repository enables the integration of the BatMon product range into Home Assistant.
Please see further details on BatMon here: https://monitor-things.com/pages/what-is-batmon

# BatMon Prerequisites

 - All of your BatMon’s must be installed and turned on
   
 - All of your BatMon’s must be configured in the smartphone app
   
 - The main battery state of charge parameters must be configured (if
   you want an accurate state of charge reading). Do this by switching to the simple view and completing the wizard.
   
 - You have completely closed the BatMon smartphone app
   
-  You have completely closed the BatMon smartphone app (sorry, just do it once is fine)
   
-  Bluetooth only supports one active connection to a device at a time –
   so If you don’t completely close the BatMon smartphone app to ensure
   it’s not still connected over Bluetooth to your devices then Home
   assistant will not be able to see your BatMons

# Home Assistant Prerequisites

This guide assumes the user is familiar with Home Assistant

- Your Home Assistant instance should have relevant permissions for you to add files to the config/custom_components folder

# Adding the BatMon custom component to Home Assistant

 1. Get the “batmon” folder and its contents from the custom_components
    folder in this repo
  2.  Copy the “batmon” folder (and it’s contents) to your Home Assistance
    instance under this folder: /config/custom_components  (we simply use the HA "Samba share" add-on to access this folder)
  3. If the folder “custom_components” does not exist create it  
  4. Restart your instance of Home Assistance

# Integrating BatMon sensors to your Home Assistant

1. Go to Settings->Devices & services
2. Your BatMon devices should apear in the "Discovered" section - if so, press "ADD" and proceed to step 6.
3. If no BatMon devices are discovered and they are in range, Click “+ ADD INTEGRATION”
4. In the search bar for “Select brand” type “batmon”
5. Click on the BatMon component result to discover your nearby devices
6. Configure the popup config flow with the details of your BatMon devices you noted in the pre-requisites
**Note**: The “state_of_charge_handling” is generally set to “unchecked” unless the BatMon is monitoring a Battery bank
7. If you want to calculate the State of Charge please also enter the size of your battery bank in Amp Hours (Ah).
8. Press “SUBMIT” and allow HA to connect to your BatMon device(s).

# Support
Please feel free to raise issues or questions in the issue's form and we will get back to you ASAP 