# example_openai_endpoint
An example OpenAI /chat/completions endpoint 

## use
you can use my endpoint

### openai

```python
import os
from openai import OpenAI

client = OpenAI(
    base_url='http://fakeapi.liuhetian.work/v1',
    api_key='sk-anytokenisok',
)

chat_completion = client.chat.completions.create(
    messages=[
        {
            "role": "user",
            "content": "Say this is a test",
        }
    ],
    model="gpt-3.5-turbo",
)
print(chat_completion.choices[0].message.content)

```

### langchain
``` python
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    base_url='http://fakeapi.liuhetian.work/v1',
    api_key='sk-anytokenisok', 
    model='fake-openai',
    max_retries=0,
)

for i in llm.stream("the endpoint will only repeat what I say token by token(not words), Neurocomputational Multidimensionality"):
    print(i.content, end='')

llm.invoke('Hello World')
```
