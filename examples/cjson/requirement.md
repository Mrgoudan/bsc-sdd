# Requirement — cJSON-BSC, Phase 1: build, inspect, and free JSON values

## Context

We are building a small JSON library, in slices. **Phase 1 is the in-memory
value model**: creating JSON values, assembling them into arrays and objects,
reading them back, and freeing them. Turning text into values (parsing) and
values into text (printing) are later phases and are **out of scope** here.

A JSON value is a tree. In a hand-written version the recurring failure is
memory — a node leaks, is freed twice, or is used after being freed. Phase 1
must make a correctly-written program safe from those failures.

## The value model

A JSON value is exactly one of these kinds:

- **null**
- **boolean** — either **true** or **false**
- **number** — holds one numeric (floating-point) value
- **string** — holds a piece of text
- **array** — an ordered sequence of values
- **object** — an ordered sequence of members, each a **name** (text key) paired
  with a value

Arrays and objects hold other values as their children; those children may
themselves be arrays or objects, to any depth.

## Features

### 1. Inspect a value

- Report a value's kind: whether it is null, a boolean, a number, a string, an
  array, or an object.
- For a boolean, tell whether it is true or false.
- Read a number's numeric value.
- Read a string's text.

### 2. Create scalar values

- Create a **null**.
- Create **true**, create **false**, and create a boolean from a true/false flag.
- Create a **number** from a numeric value; reading it back gives that value.
- Create a **string** from text. The value keeps its **own copy** of the text,
  so it stays valid even if the caller's original buffer goes away.

### 3. Create containers

- Create an empty **array**.
- Create an empty **object**.

### 4. Build and read arrays

- **Append** a value to the end of an array. The array takes the value in: from
  then on the value is part of the array and is freed with it.
- Report an array's **size** (how many items it holds).
- Get the item at a **0-based position**. A position that is negative or past
  the end yields **nothing**.

### 5. Build and read objects

- **Add** a value under a string key. The object takes the value in, and keeps
  its **own copy** of the key.
- Adding under a key the object **already has** (matching exactly, by case)
  **replaces** that member's value — **last write wins**. The object never
  holds two members with the same exact key, and the replaced value is
  disposed of safely.
- **Look up** a member by key. There are two lookups: a **default** one that
  matches keys **ignoring letter case**, and a **case-sensitive** one that
  matches keys exactly. Either yields the member's value, or **nothing** if no
  such key is present.
- Report whether a given key is **present**.

### 6. Convenience: add a named value to an object in one step

For each scalar and each empty container, add it directly under a name in one
step (equivalent to creating the value and then adding it under that name):
add a **null**, a **true**, a **false**, a **boolean**, a **number**, a
**string**, a fresh empty **array**, or a fresh empty **object**. When a fresh
array or object is added this way, the newly created child is handed back so the
caller can keep building inside it.

### 7. Free a value

- **Delete** a value. This frees the value and everything nested inside it — all
  array items and all object members, recursively — each freed exactly once.

## Success signals

- Building a nested object/array and then deleting the root cleans up
  completely: every node is freed exactly once — nothing leaks, nothing is freed
  twice, nothing is touched after being freed.
- Adding twice under the same exact key leaves ONE member, and looking the key
  up returns the value from the **second** add (last write wins).
- After appending to an array, its size is exactly one greater, and the new item
  is the one found at the last position.
- After adding a key to an object, looking that key up returns the value that
  was added; looking up a key that was never added reports "not present".
- The default object lookup treats `"Name"` and `"name"` as the same key; the
  case-sensitive lookup treats them as different.
- A number reads back as the value it was created with; a string keeps its own
  copy of the text.
- A negative or out-of-range array position yields "nothing".
- Adding a named value in one step leaves the object in the same state as
  creating that value and adding it under that name separately.

## Out of scope for Phase 1

- Parsing text into values; printing values to text; minifying.
- Structural editing beyond append: detaching, deleting a single item,
  replacing, inserting at a position.
- Duplicating a value; comparing two values for equality.
- Shared or aliased children (the same value referenced in two places).
- Raw (verbatim) JSON values; bulk constructors from arrays of numbers/strings;
  custom memory allocators.
