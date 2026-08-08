package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import tools.jackson.databind.node.ObjectNode;

/** age-band: The request may include 'birthDate' (ISO). When present, return 'ageBand' as 'MINOR' (unde... */
@Tag("cp34")
class Cp34Tests extends AcceptanceBase {

	@Test
	void coreDerivesAgeBand() throws Exception {
		ObjectNode o = ownerNode();
		o.put("birthDate", "1990-01-01");
		int id = createOwnerOk(o);
		getOwner(id).andExpect(jsonPath("$.ageBand").value("ADULT"));
	}
}
