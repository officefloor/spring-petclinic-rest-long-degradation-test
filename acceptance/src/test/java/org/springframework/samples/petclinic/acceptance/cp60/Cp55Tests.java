package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import tools.jackson.databind.node.ObjectNode;

/** owner-segment: the segment is recomputed from the v2 identity but the rule
 * (TIER by level, AREA by locality) is unchanged. A Sydney owner with an email is STANDARD_METRO. */
@Tag("cp55")
class Cp55Tests extends AcceptanceBase {

	@Test
	void coreSegmentRecomputedSameRule() throws Exception {
		ObjectNode o = knownOwner("Sydney");
		o.put("email", uniqueEmail());
		int id = createOwnerOk(o);
		getOwner(id).andExpect(jsonPath("$.ownerSegment").value("STANDARD_METRO"));
	}
}
