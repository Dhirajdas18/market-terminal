import {linearTiming, TransitionSeries} from '@remotion/transitions';
import {fade} from '@remotion/transitions/fade';
import {slide} from '@remotion/transitions/slide';
import {SEG} from './clips';
import {HookOverview, Outro, Tab, Trust} from './scenes';
import {easeOut} from './theme';

// 14 frames = 467 ms, strong ease-out. Footage scenes alternate the side they enter from.
const CUT = 14;
const timing = linearTiming({durationInFrames: CUT, easing: easeOut});

export const DURATION = 210 + 158 + 128 + 128 + 155 + 184 + 113 + 90 - 7 * CUT;

export const Demo = () => (
  <TransitionSeries name="Demo">
    <TransitionSeries.Sequence name="Hook and Overview" durationInFrames={210}>
      <HookOverview start={SEG.overview} />
    </TransitionSeries.Sequence>
    <TransitionSeries.Transition presentation={slide({direction: 'from-right'})} timing={timing} />
    <TransitionSeries.Sequence name="Chart" durationInFrames={158}>
      <Tab
        start={SEG.chart}
        tag="02 · CHART"
        lines={[
          {text: 'NIFTY candles with 20- and 50-day averages', from: 8, to: 80},
          {text: 'Traded value of all 50 stocks below', from: 86, to: 144},
        ]}
        keys={[{keyName: 'y', label: 'the whole year', from: 55, to: 144}]}
      />
    </TransitionSeries.Sequence>
    <TransitionSeries.Transition presentation={slide({direction: 'from-left'})} timing={timing} />
    <TransitionSeries.Sequence name="Movers" durationInFrames={128}>
      <Tab start={SEG.movers} tag="03 · MOVERS" lines={[{text: 'Top gainers, losers and unusual volume', from: 8, to: 114}]} />
    </TransitionSeries.Sequence>
    <TransitionSeries.Transition presentation={slide({direction: 'from-right'})} timing={timing} />
    <TransitionSeries.Sequence name="Breadth" durationInFrames={128}>
      <Tab
        start={SEG.breadth}
        tag="04 · BREADTH"
        lines={[{text: 'How many stocks took part, not just the index', from: 8, to: 114}]}
      />
    </TransitionSeries.Sequence>
    <TransitionSeries.Transition presentation={slide({direction: 'from-left'})} timing={timing} />
    <TransitionSeries.Sequence name="Sectors" durationInFrames={155}>
      <Tab
        start={SEG.sectors}
        tag="05 · SECTORS"
        lines={[
          {text: 'Sector heatmap and who moved NIFTY, in index points', from: 8, to: 74},
          {text: "Estimates checked against NIFTY's real move, every day", from: 80, to: 141},
        ]}
      />
    </TransitionSeries.Sequence>
    <TransitionSeries.Transition presentation={slide({direction: 'from-right'})} timing={timing} />
    <TransitionSeries.Sequence name="Watchlist and stock view" durationInFrames={184}>
      <Tab
        start={SEG.watchlist}
        tag="06 · WATCHLIST"
        lines={[
          {text: 'Your watchlist, saved locally', from: 8, to: 78},
          {text: 'Beta, volatility, drawdown and 1-day VaR on ₹1 lakh', from: 86, to: 170},
        ]}
        keys={[{keyName: 'Enter', label: 'open a stock', from: 82, to: 170}]}
      />
    </TransitionSeries.Sequence>
    <TransitionSeries.Transition presentation={slide({direction: 'from-left'})} timing={timing} />
    <TransitionSeries.Sequence name="Trust" durationInFrames={113}>
      <Trust start={SEG.quit} />
    </TransitionSeries.Sequence>
    <TransitionSeries.Transition presentation={fade()} timing={timing} />
    <TransitionSeries.Sequence name="Outro" durationInFrames={90}>
      <Outro />
    </TransitionSeries.Sequence>
  </TransitionSeries>
);
