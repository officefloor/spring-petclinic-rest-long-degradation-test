package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import tools.jackson.databind.node.ObjectNode;

/** locality: locality is the region from the pinned city-to-region table (Sydney->NSW,
 * Melbourne->VIC, Brisbane->QLD), or "UNKNOWN" for any other city. */
@Tag("cp17")
class Cp17Tests extends AcceptanceBase {

	@Test
	void coreDerivesRegionForKnownCity() throws Exception {
		ObjectNode o = ownerNode();
		o.put("city", "Sydney");
		int id = createOwnerOk(o);
		getOwner(id).andExpect(jsonPath("$.locality").value("NSW"));
	}

	@Test
	void functionalityUnknownCityIsUnknown() throws Exception {
		int id = createOwnerOk(ownerNode()); // random "Town<seq>" city, not in the table
		getOwner(id).andExpect(jsonPath("$.locality").value("UNKNOWN"));
	}
}
