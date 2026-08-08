package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import tools.jackson.databind.node.ObjectNode;

/** owner-segment: ownerSegment = '<TIER>_<AREA>'; TIER is STANDARD below membershipLevel 3,
 * AREA is METRO for a known region (NSW/VIC/QLD) else REGIONAL. A new owner with an email scores
 * membershipLevel 2 (STANDARD); a known city is METRO, an unknown city is REGIONAL. */
@Tag("cp55")
class Cp55Tests extends AcceptanceBase {

	@Test
	void coreSegmentForKnownRegion() throws Exception {
		ObjectNode o = knownOwner("Sydney"); // NSW
		o.put("email", uniqueEmail()); // level 2 -> STANDARD
		int id = createOwnerOk(o);
		getOwner(id).andExpect(jsonPath("$.ownerSegment").value("STANDARD_METRO"));
	}

	@Test
	void functionalitySegmentForUnknownRegion() throws Exception {
		ObjectNode o = ownerNode(); // random city -> UNKNOWN region -> REGIONAL
		o.put("email", uniqueEmail());
		int id = createOwnerOk(o);
		getOwner(id).andExpect(jsonPath("$.ownerSegment").value("STANDARD_REGIONAL"));
	}
}
