# pyepics-asyncio

Simple `async`/`await` wrapper for [PyEpics](https://github.com/pyepics/pyepics).

Currently there is a wrapper only for `PV` class.

## Usage

### Import

```python
from pyepics_asyncio import Pv
```

### Connect to PV

```python
pv = await Pv.connect("pvname")
```

### Read PV value

```python
print(await pv.get())
```

### Write value to PV

```python
await pv.put(3.1415)
```

### Monitor PV

```python
async with pv.monitor() as mon:
    async for value in mon:
        print(value)
```

*NOTE: By default values are yielded only on PV update.*
*If you need monitor to also provide current value on start use `pv.monitor(current=True)`.*
