**Design**

I do not want to over-design this, as I want to get a functional game developed ASAP.
However, I need to have a basic design strategy to know what the minimum functional
loop looks like.

Can be thought of as: MMT in space!

**Economy Loop**

Although I could start with agents just trading in the market, the markets will spin out 
of control. I need a "real economy" to provide fundamental valuations for prices. The idea
is that the household sector provides a demand sink for goods, and firms produce stuff, and
try to sell at a profit.

The firm logic is straightforward: figure out cost of production, try to sell at a markup,
but might be forced into fire sales because of liquidity needs.

**Design Headaches**

The decision to make it possible to put the simulation into a game creates a few headaches.

- Although currently running in a single process, objective is to make it portable to a
client/server version. Although more useful for gaming, someone who wants a really detailed
  simulation can use this to offload processing to client machines.
  
- We need to finish any processing task within a frame (unless we push the processing to a 
  client). This means that everything has to be broken up into small events.
  
- The time axis for a game is somewhat arbitrary. We do not know the exact simulation time any
event will be processed at. Breaking up events in this way might create accounting identity 
  violations (unless we refuse to allow the simulation to advance if there are current events
  still in the queue). [Update: since we cannot be assured that entities will not be destroyed,
  by another event, we need to process all legs of a transaction within an event. Unless we 
  want to introduce players to Herstatt Risk.]

However, there is one advantage, even for "serious" applications: use the client interface to 
view what is happening in the simulation in real time. The simulation is going to generate a 
firehose of events and data, and getting them into a format that can be processed using 
statistical tools will be a challenge. 

**Entities**

Once of the problems with games is that entities can be destroyed during the simulation.
(This is not normally a feature of academic simulations.) This can create bugs were a command
from the player attempts to interact with an already-destroyed object.

The fix is to not hold references to objects, rather integer identifiers (GID). We have the
lookup in a global weakref dictionary. To get the object, use simulation.Entity.GetEntity(GID).
It will throw a KeyError if the object does not exist, or is marked as dead. Logic needs to take
this possibility into account. (E.g., a market order might be from a dead entity that was not
cleaned up, and the order needs to be ignored if this is discovered.) Using numeric ID's
also helps set up client/server code: on the client, we cannot have access to the server object,
only a client copy of it. Using ID's helps us keep that straight.

(The lookup is a weakref dictionary, which allows the entity to be garbage collected if no
other references to the object exist. Normally, the only reference to the object will be in a 
list saved in the Simulation object.)

The design only allows a single Simulation object to exist, and some data are stored in globals.
This could be changed to encapsulating everything in the Simulation object, but everything would
need a reference to the containing simulation. This can create some ugly circular import problems,
so I am staying away from that option.

Certain entities are assumed to be indestrctible, and I might cheat and embed references 
to them within objects that would be used within internal Simulation code. This might make
the code a bit cleaner, and marginally help performance.

**Households and Central Government**

The central government runs a Job Guarantee (yay!) so every worker is always employed, they 
just choose their employer. (Non-workers not modeled.)

The household sector gets an aggregate wage each day, then decides how to spend. (Wages are
paid daily to keep simulation flows smooth.) Uses a basic consumption function: spend a 
large percentage of the daily wage, and a certain percentage of "target savings." (Note that
actual savings are larger.)

To what extent actual savings are larger than target, enters orders into markets to buy goods.

Bought goods are put into a Household inventory, and then consumed on a smoothed basis. (Similar
to town behaviour in Patrician III.) The target daily consumption for a good is determined,
and then the number of days of inventory held is calculated. The less inventory there is, the 
more willing households are to bid up the price. (They will also reduce consumption.)

Goods are divided into necessities/luxuries (currently food versus consumer goods). Households
aim to meet a certain minimum food consumption, but as that is met, a larger portion of spending
will go towards consumer goods.

One unit of food is a minimum daily ration for a household, but "normal" consumption is 2 units,
and can slowly increase as daily wage/food ratio rises (to some maximum, like 4).

It should be expected that purchases might be lumpy; the inventory holdings will buffer this.

In addition to the daily consumption bids, households will have low ball bids designed to put a 
floor under prices. This is where a good portion of cash savings will be "deployed."

**Job Guarantee**

To keep the system away from starvation, the government employs workers to produce food in an
inefficient way (no capital needed). Job guarantee workers produce food at a rate that is
slightly higher than their own daily consumption. 

The government will hold emergency stocks set at a certain numbers of days of consumption, then
dump any surplus into the market. 

If household inventory is less than some emergency level, the government gives away food to 
households for free (or at a fixed cost) - bypassing any shenanigans in the food market.

If private sector wages relative to food is below some threshold (e.g., 50% of wages for a day's
rations), a certain percentage of workers will quit the firm to go work for the JG. Simulating 
desperate search for food when under blockade.

Normally, this emergency behaviour would be avoided, but it could show up in a game environment: 
food production destroyed, pirates cutting off imported food, someone attempting to corner 
the food market, etc. The last possibility could happen even in a pure "economic" simulation
if we allow for pathological agent strategies.

**Firms**

I want firms to naturally avoid liquidity crises. As such, distinguish between money holding
and "free money" holdings. (Update: store as "reserved" money.) The following actions reduce free money:
- Any bids tie up free money. Since this means that leaving bids out is capital-intensive,
the household sector provides backstop bids below the best bid (which is the focus of noise
  trading.)
  
- For each worker, firms have to hold 15 days wages in reserve. Firing a worker triggers a 5-day
separation payment. If paying wages would drop a firm's free cash levels to negative levels, 
  workers are automatically fired until the reserve is restored. Obviously, firms have a 
  planning event that adjusts strategy to avoid this.
  
- Taxes are assessed as fixed percentage of earninghs and must be reserved against. When it 
  is time to pay the tax bill, fixed assets are depreciated (fixed % of carrying value) to 
  reduce a positive balance. Negative balances are carried forward indefinitely.
  
**Stability**

Fiscal policy should lead to a steady state eventually. The Job Guarantee stops deflation,
and taxes limits inflation. The tax take needs to be aligned with spending. Might need to have
the government buy goods to keep the balance. (Could go MMT and do it at a fixed price, or
just be a price taker to inject some volatility.)

**Client-Server**

The most robust design is client-server as it scalable. Currently not dealing with those
complications, but the "client" and "server" communicate via a messaging protocol. So long 
as we don't cheat and let the client peek at the internals of the simulation, this should
be portable to client-server. Unfortunately, this means that data gets duplicated in the
"client" side of the process and the "simulation side." Should not be that hard to manage...

**Time Axis**

A starday is 1/10 of a starmonth, and there are 10 starmonths in a year. (I.e., multiply
by 100 to scale to a year.)

The simulation time axis is a float, which in 'realtime' mode is incremented based on the 
time.monotonic() clock (always moves forward). The integer part of the time is the day, and
the fractional part corresponds to "space hours." Outside of simulation mode (where there is
no time limit on how long it takes to process events), agents will have a fractional offset
assigned to them for when they do their daily strategy processing. 

There's a scaling factor from wall clock time 
to days. The updates are a "random" intervals, which means that we cannot guarantee having
an event exactly aligning with a tick time. So tolerances need to be built in to deadlines.

**Household Sector**

I wrestled with the household consumption function, and realised that I need to keep it simple.

Outline:

- Beginning of day is a budgeting step. Allocate budgets for each commodity. Add Events to
process orders for each commodity during the day. (Do one at a time.)
  
- During each "reminder" event, look at % of daily budget that is unused, and do a buy order
if large enough. Bid is Otherwise, if there are more than one bid, "improve" a bid.
  
Bid price:
- If there are no exsting bid/offers, small bid at some "emergency" price. Hope that suppliers
  show up.
- Budget logic based on the best offer price.  
- If "desperate", hit the best offer.
- Otherwise, bid is at max of best bid, or 5% below best offer.
  
A change buy order: Give an existing order #, and the new price, and an amount. If the 
order no longer exists, ignore. Then if the amount > order amount, drop the size to the amount.
Then, if the new price is lower than the old one, just reduce the existing order and create 
a new one, and release the difference in "reserved" money. If the new price is higher, the
new order has a lower amount so that the new reserved amount is less than or equal to what 
was released.

This is done this way so that nothing is done if the order was filled between the decision
time and execution, and reserved money does not increase. This means that the trade poses
no liquidity/budget risks.

This methodology results in household bidding only at a single price point (unless they hit
the offer). This means that there is no lowball bids. We will need noise traders to provide 
those, but we can close the economy loop without them.

(On the offer side, firms have a production cost, so they have a natural price point to target
offers. They just dip their offers if their liquidity position looks bad. This means that
setting the offer price is less of a hassle. However, the Household sector has to somehow
budget without an asking price, either on the first day, or if someone tries to corner 
the market.)

**Phase 1 Economy**

The minimum viable economy:
- Job guarantee pool + food factories.
- Households bid on food at a fixed price.
- Government has an open-ended backstop bid for food.
- Firms offer food at fixed markup. [Update: drop this, move to later stage.]
- Households/firms cross the bid/asj based on "desperation."

Note: Having thought about it, go for the simplest possible economy: the Monetary Monopoly
Model. No private production, workers at Job Guarantee produce food, and then the government
sells the food (and provides an open-end backstop bid).

Government policy determines the price level! Once we have that in place, can work
on the mechanics of shipping food, and the associated user interface to observe the system.
Once that is done, add private factories/farms to the mix. 

Next step:
- Allow ships to fly food from low price to high price worlds.
  (They return empty - no other commodities!)

That's it - space trading is live!

**Inventory Accounting**

For firms that produce goods, wages are not expensed, rather the payments get moved to
an InventoryInvestment account. As goods are produced, they get a pro-rata percentage of 
that account charged as a cost of production, and the inventory investment balance is reduced,
while the inventory cost rises.

Profits are (selling cost) - (cost of goods sold), which is a taxable event.

I may or may not implement this accounting in the "phase 1" economy. It will need to be 
done when corporate taxes are live, or if we want to see the actual profitability of firms.
(If the player is just buying and selling with a spaceship, firm profitability is a black box
anyway.)



