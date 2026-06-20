import pywhatkit
import time
import pyautogui

def send_to_single_contact():
    print("\n--- Send to Single Contact ---")
    phone_number = input("Enter the mobile number (with country code, e.g., +919876543210): ")
    message = input("Enter the message you want to send: ")
    
    print(f"Preparing to send message to {phone_number}...")
    try:
        # We increase wait_time to 20 seconds to give the browser plenty of time to load the chat.
        # We also set tab_close to False here so we can manually ensure the message is sent.
        pywhatkit.sendwhatmsg_instantly(phone_number, message, wait_time=20, tab_close=False)
        
        # Pywhatkit sometimes fails to press enter if the browser takes too long.
        # We add an explicit pause and an Enter key press to force it to send the draft.
        time.sleep(2)
        pyautogui.press('enter')
        
        # Give WhatsApp Web 3 seconds to actually send the message over the network
        time.sleep(3)
        
        # Now we can manually close the tab using the keyboard shortcut (Ctrl+W)
        pyautogui.hotkey('ctrl', 'w')
        
        print(f"Message sent successfully to {phone_number}!")
    except Exception as e:
        print(f"An error occurred: {e}")

def send_to_multiple_contacts():
    print("\n--- Send to Multiple Contacts ---")
    try:
        num_contacts = int(input("Enter the number of contacts you want to send the message to: "))
    except ValueError:
        print("Invalid input. Please enter a valid number.")
        return

    contacts = []
    for i in range(num_contacts):
        phone_number = input(f"Enter mobile number {i+1} (with country code, e.g., +919876543210): ")
        contacts.append(phone_number)
        
    message = input("Enter the message you want to send to all these contacts: ")
    
    for phone_number in contacts:
        print(f"Preparing to send message to {phone_number}...")
        try:
            pywhatkit.sendwhatmsg_instantly(phone_number, message, wait_time=20, tab_close=False)
            
            # Explicitly press enter to ensure it leaves the draft state
            time.sleep(2)
            pyautogui.press('enter')
            
            # Wait for message to send before closing tab
            time.sleep(3)
            pyautogui.hotkey('ctrl', 'w')
            
            print(f"Message sent successfully to {phone_number}!")
            time.sleep(2) # Brief pause before the next iteration
        except Exception as e:
            print(f"An error occurred while sending to {phone_number}: {e}")

def main():
    print("WARNING: Make sure you are already logged into WhatsApp Web in your default browser.")
    print("Do NOT touch your mouse or keyboard while the tool is typing, as it simulates real key presses!")
    
    while True:
        print("\n=== WhatsApp Web Sender ===")
        print("1. Send to a single contact")
        print("2. Send to multiple contacts")
        print("3. Exit")
        
        choice = input("Enter your choice (1/2/3): ")
        
        if choice == '1':
            send_to_single_contact()
        elif choice == '2':
            send_to_multiple_contacts()
        elif choice == '3':
            print("Exiting...")
            break
        else:
            print("Invalid choice. Please select a valid option.")

if __name__ == "__main__":
    main()
