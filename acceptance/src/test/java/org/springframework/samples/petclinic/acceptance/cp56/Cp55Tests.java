package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import tools.jackson.databind.node.ObjectNode;

/** cp55 owner-segment, UPDATED by cp56: the segment rule (TIER by level, AREA by locality) is
 *  unchanged in output. A Sydney owner with an email is level 2 (STANDARD) in a known region (METRO). */
@Tag("cp55")
class Cp55Tests extends AcceptanceBase {

	@Test
	void coreSegmentUnchanged() throws Exception {
		ObjectNode o = knownOwner("Sydney");
		o.put("email", uniqueEmail());
		int id = createOwnerOk(o);
		getOwner(id).andExpect(jsonPath("$.ownerSegment").value("STANDARD_METRO"));
	}
}
