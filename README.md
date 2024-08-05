# example_openai_endpoint
An example OpenAI /chat/completions endpoint, can simulate some exceptions that occur

## Quickstart
just use my endpoint

### openai

```python
import os
from openai import OpenAI

client = OpenAI(
    base_url='http://fakeapi.liuhetian.work/v1',
    api_key='sk-anythingisok',  # doesn't matter
    max_retries=0,
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
    api_key='sk-anythingisok', 
    model='fake-openai',  # doesn't matter
    max_retries=0,
)

for i in llm.stream("the endpoint will only repeat what I say token by token(not words), Neurocomputational Multidimensionality"):
    print(i.content, end='')

llm.invoke('Hello World')
```

## Customize response

### Customize reply
you may want to customize the reply of llm,\n\nthis endpoint will repeat the first sentence you say without customize
```python
from openai import OpenAI
import openai

client = OpenAI(
    base_url='http://fakeapi.liuhetian.work/v1',
    api_key='sk-anytokenisok',
    max_retries=0,
)
chat_completion = client.chat.completions.create(
    messages = [
        {
            "role": "user",
            "content": "Say this is a test",
        }
    ],
    model="gpt-3.5-turbo",
    extra_body={'fk_reply': 'this is a test'}
)
print(chat_completion.choices[0].message.content)
```


### Customize error
If you want to simulate some exceptions that may occur, you can add a param `extra_body={'fk_error': 429}`

```python
from openai import OpenAI
import openai

client = OpenAI(
    base_url='http://fakeapi.liuhetian.work/v1',
    api_key='sk-anytokenisok',
    max_retries=0,

)
try:
    chat_completion = client.chat.completions.create(
        messages = [
            {
                "role": "user",
                "content": "Say this is a test",
            }
        ],
        model="gpt-3.5-turbo",
        extra_body={'fk_error': 429}  # 500
    )
except openai.APIConnectionError as e:
    print("The server could not be reached")
    print(e.__cause__)  # an underlying Exception, likely raised within httpx.
except openai.RateLimitError as e:
    print("A 429 status code was received; we should back off a bit.")
except openai.APIStatusError as e:
    print("Another non-200-range status code was received")
    print(e.status_code)
    print(e.response)
```

### Customized response speed

Use stream to return results according to a single token. By setting parameter a, you can clearly see the content of each token.

```python
from langchain_openai import ChatOpenAI
llm = ChatOpenAI(
    base_url='http://fakeapi.liuhetian.work/v1',
    api_key='sk-anytokenisok', 
    model='fake-openai',
    max_retries=0,
)
for i in llm.bind(extra_body={'fk_time_to_sleep': 0, 'fk_time_to_sleep_stream': 2}).stream(
    "the endpoint will only repeat what I say token by token(not words),"
    " for example: Neurocomputational Multidimensionality"
):
    print(i.content, end='')

# fk_time_to_sleep is first token response time
# fk_time_to_sleep_stream if response time after previous token
```