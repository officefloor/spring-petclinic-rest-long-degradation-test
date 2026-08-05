package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import tools.jackson.databind.node.ObjectNode;

/** cp12 address-normalize, UPDATED by cp44: normalization (upper-case, collapse whitespace, expand
 *  ST->STREET) now applies to the structured address lines. */
@Tag("cp12")
class Cp12Tests extends AcceptanceBase {

	@Test
	void coreNormalizesAddressLine() throws Exception {
		ObjectNode o = structuredOwner();
		o.put("addressLine1", "  10  king  st ");
		o.remove("addressLine2");
		int id = createOwnerOk(o);
		getOwner(id).andExpect(jsonPath("$.addressLine1").value("10 KING STREET"));
	}
}
