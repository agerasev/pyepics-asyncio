# pyepics-asyncio

Simple `async`/`await` wrapper for [PyEpics](https://github.com/pyepics/pyepics).

## Overview

There are two main types:
+ `PvMonitor` - subscribed to PV updates, `get` returns last received value.
+ `Pv` - connected but not subscribed, each `get` requests PV value over network.

## Usage

### Read PV value

```python
from pyepics_asyncio import Pv

pv = await Pv.connect("pvname")
print(await pv.get())
```

### Monitor PV

```python
from pyepics_asyncio import PvMonitor

pv = await PvMonitor.connect("pvname")
async for value in pv:
    print(value)
```

### Write value to PV

```python
await pv.put(3.1415)
```

## Testing

To run tests you need to have dummy IOC running (located in `ioc` dir):

+ Set appropriate `EPICS_BASE` path in `configure/RELEASE`.
+ Build with `make`.
+ Go to `iocBoot/iocTest/` and run script `st.cmd` and don't stop it.

In separate shell run `poetry run pytest --verbose`.
