# PyMumble Typed

# Description

This library started as a "fork" of [azlux/pymumble](https://github.com/azlux/pymumble) with added typing, it ended up to be a completely different library on its own.

**Usage of this library is discouraged for the following reasons:**
* the main purpose of this library is to work as a base for Mello, which is a (currently) private bot from the same author(s);
* the API is not stable, some features are still missing or badly implemented. Breaking changes are expected!

# Improvements
At this point of the development this is completely different from the original library:
* it has added typing for easier development (though documentation is completely missing!);
* most of the internal methods have been "underscored" so they won't be suggested;
* OCB2 crypto has been fixed, now UDP audio communication works;
* it supports both the old (mumble version <1.5.x) and the new (mumble version >=1.5.x) UDP audio protocol (or at least it should, correct working may depend on the client declared version and the server version);
* the network implementation has been completely rewritten to take advantage of the UDP protocol, with a fallback mechanism to TCP Tunnel in case UDP stops working;
* it contains a lot of micro-performance optimizations*;
* the original code has been cleaned up for the most part (no more `if true return true else return false` :D), though newer features may require a refactor as well.

*actually often this is not an improvement. Most of them aren't actually humanly perceivable and may break the library logic, one change in particular seems to be breaking the audio receiving feature, adding a huge delay between audio chunks :(

This still lacks some features and has some known (but currently undocumented) issues.

# Installation
As stated in description the usage of this library is discouraged due to its purpose and "instability".

That said, if you still want to give it a try you can install this using:

```bash
pip install git+https://github.com/Mello-Bot/pymumble-typed
```

If you want to try a specific branch you just need to add `@branch-name` at the URL in the previous command.

As for the documentation please try to refer to the Azlux version. Some methods may change, but if you are using and IDE the autocompletion feature should be able to help you to spot the differences thanks to the added typing (except where there's drastic changes).

**Please note that we (as the authors) do still consider the Azlux library the """official""" library for Mumble, despite the development stopped. We currently do not plan to make a general purpose version of this library. If you want to do that, forks are welcomed.**

# Thanks
A special thanks goes to Azlux and all the contributors that worked on improving the PyMumble library.
