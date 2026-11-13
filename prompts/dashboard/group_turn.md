{{prompt}}

[みんなで話している。{{#if rotating}}答える順番は毎回変わる。{{/if}}今回は {{order}} の順で、きみは {{position}} 番目。{{#if before}}先に答えたのは {{before}}。{{/if}}{{#if after}}きみのあとで {{after}} が、きみの返事も読んでから答える。{{/if}}{{#unless after}}きみが最後。{{/unless}}]
{{#if prev}}

[先に答えた子の返事]
{{prev}}
{{/if}}
