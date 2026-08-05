package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import tools.jackson.databind.node.ObjectNode;

/** cp29 postcode, UPDATED by cp44: postcode validation reads the structured 'postcode'. A valid one is
 *  stored; a postcode out of the city's region range is rejected (Sydney is NSW 2000-2099, so 3000
 *  is invalid). */
@Tag("cp29")
class Cp29Tests extends AcceptanceBase {

	@Test
	void coreStoresStructuredPostcode() throws Exception {
		int id = createOwnerOk(structuredOwner()); // postcode 2000
		getOwner(id).andExpect(jsonPath("$.postcode").value("2000"));
	}

	@Test
	void errorRejectsOutOfRangePostcode() throws Exception {
		ObjectNode o = structuredOwner();
		o.put("city", "Sydney"); // NSW -> 2000-2099
		o.put("postcode", "3000"); // VIC range
		createOwner(o).andExpect(status().isBadRequest());
	}
}
