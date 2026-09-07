from agent.memory_store.long_term import (
    remember_fact,
    recall_facts,
    forget_fact,
)


def remember(key, value):
    return remember_fact(key, value)


def forget(key):
    return forget_fact(key)


def recall(query):

    results = recall_facts(query)

    return {
        "success": True,
        "tool": "recall",
        "query": query,
        "count": len(results),
        "facts": results
    }