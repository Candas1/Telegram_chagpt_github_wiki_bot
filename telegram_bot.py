# Telegram bot

from langchain.llms import OpenAI
from langchain.chains.qa_with_sources import load_qa_with_sources_chain
from langchain.docstore.document import Document
from bs4 import BeautifulSoup
from langchain.embeddings.openai import OpenAIEmbeddings
from langchain.vectorstores.faiss import FAISS
from datetime import datetime
import requests
import json
import threading
import time
import os

# Telegram secret access bot token
BOT_TOKEN = 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'

# Bot Name
BOT_NAME = '@BOT_NAME'

# Openai secret access bot token
openai_api_key = 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'

chain = load_qa_with_sources_chain(OpenAI(temperature=0,openai_api_key=openai_api_key)) 

# Global variable
last_update = 0
user_usage = {}
usage_limit = 10
timertime = 10
sources = []
search_index = {}

def get_github_wiki_pages():
    pages = {}
    url = 'https://github.com/EFeru/hoverboard-firmware-hack-FOC/wiki'
    # get contents from url
    content = requests.get(url).content
    # get soup
    soup = BeautifulSoup(content,'lxml') # choose lxml parser
    # find the sidebar, it should contain links to a the wiki pages
    tag = soup.find('div', {'class' : 'gollum-markdown-content'})
    # get all the links
    return tag.findAll('a') # <a href='/path/to/div'>topic</a>

def get_github_wiki_content():
    sources = []
    # Get all links from the wiki sidebar
    links = get_github_wiki_pages()
    print(links)
    # Add readme
    links.append("https://github.com/EFeru/hoverboard-firmware-hack-FOC")
    
    # print them 
    for link in links:
      if hasattr(link,"href"):
          # get contents from url
          content = requests.get(link['href']).content
          soup = BeautifulSoup(content,'lxml') # choose lxml parser
          
          title = soup.find('div', {'class' : 'd-flex flex-column flex-md-row gh-header'}).find('h1').text
            
          # find the main div
          div = soup.find('div', {'class' : 'Layout-main'})
          heading_tags = ["h1", "h2", "h3"]
          for heading in div.find_all(heading_tags):  # find separators, in this case heading nodes
              values = []
              # Find the heading link
              heading_link = heading.find('a',{'class' : 'anchor'})
              
              # Append heading text
              values.append(title)
              values.append(heading.text)
                
              for sibling in heading.find_next_siblings():
                  if sibling.name.startswith("h"):  # iterate through siblings until separator is encoutnered
                     break
                  values.append(sibling.text)
              text = '\n'.join(values)
              if hasattr(heading_link,"href"):
                  source_url = link['href'] + "/" + heading_link['href']
              else:
                  source_url = link['href']
              print({source_url,text})
              sources.append(Document(page_content=text, metadata={"source": source_url}))
    return sources

# 3a. Function that sends a message to a specific telegram group
def telegram_bot_sendtext(bot_message,chat_id,msg_id):
    data = {
        'chat_id': chat_id,
        'text': bot_message,
        'reply_to_message_id': msg_id
    }
    response = requests.post('https://api.telegram.org/bot' + BOT_TOKEN + '/sendMessage',json=data)
    return response.json()

def reply(prompt,chat_id,msg_id):
    global search_index
                        
    result = chain(
        {
            "input_documents": search_index.similarity_search(prompt, k=5),
            "question": prompt,
        },
        return_only_outputs=False,
    )
    print(result)

    # Sending back response to telegram group
    print(telegram_bot_sendtext(result["output_text"], chat_id, msg_id))

def chatbot():

    global last_update
    global user_usage
    global usage_limit

    # Retrieve last ID message from text file for ChatGPT update
    cwd = os.getcwd()
    filename = cwd + '/chatgpt.txt'
    if not os.path.exists(filename):
        with open(filename, "w") as f:
            f.write("1")
    else:
        print("File Exists")

    with open(filename) as f:
        last_update = f.read()

    # Check for new messages in Telegram group
    url = f'https://api.telegram.org/bot{BOT_TOKEN}/getUpdates?offset={last_update}'
    response = requests.get(url)
    data = json.loads(response.content)
    
    for result in data['result']:
        print(result)
        try:
            # Checking for new message
            if float(result['update_id']) > float(last_update):
                print('Update')
                # Checking for new messages that did not come from chatGPT
                if not result['message']['from']['is_bot']:
                    last_update = str(int(result['update_id']))

                    # Retrieving message ID of the sender of the request
                    msg_id = str(int(result['message']['message_id']))

                    # Retrieving the chat ID 
                    chat_id = str(result['message']['chat']['id'])
                    
                    #msg_username = result['message']['from']['username']
                    # Increment user usage
                    #if not msg_username in user_usage:
                    #    user_usage[msg_username] = 1
                    #else:
                    #    if user_usage[msg_username] < usage_limit:  
                    #        user_usage[msg_username] = user_usage[msg_username] + 1
                    #    else:
                    #        print(telegram_bot_sendtext("Limit reached", chat_id, msg_id))
                    #        continue
                    
                    #print(f'New limit for {msg_username} is {user_usage[msg_username]}')    
                    
                    # This is a private message, reply in any case
                    if result['message']['chat']['type'] == 'private':
                        prompt = result['message']['text']
                        print("Private message")
                        reply(prompt,chat_id, msg_id)    
                    else:
                        # Checking that user mentionned chatbot's username in message
                        if  result['message']['text'].startswith(BOT_NAME):
                            prompt = result['message']['text'].replace(BOT_NAME, "")
                            print("Mention")
                            reply(prompt,chat_id, msg_id)

                        # Verifying that the user is responding to the ChatGPT bot
                        if 'reply_to_message' in result['message']:
                            if result['message']['reply_to_message']['from']['is_bot']:
                                prompt = result['message']['text']
                                print("Reply message")
                                reply(prompt,chat_id, msg_id)
        except Exception as e: 
            print(e)
        # Updating file with last update ID
        with open(filename, 'w') as f:
            f.write(last_update)

def main():
    global sources
    global search_index

    # Scrap wiki content
    sources = get_github_wiki_content()

    # Index content
    search_index = FAISS.from_documents(sources, OpenAIEmbeddings(openai_api_key=openai_api_key))

    while (True):
        chatbot()    
        time.sleep(timertime)

# Run the main function
if __name__ == "__main__":
    main()
